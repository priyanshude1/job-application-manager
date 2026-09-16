import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database import crud
from src.database.connection import get_db
from src.llm.cover_letter import generate_and_compile_cover_letter
from src.llm.cv_tailoring import tailor_and_compile_cv
from src.llm.scoring import score_match
from src.tracking.mlflow_tracker import log_generation_run

router = APIRouter(prefix="/generate", tags=["generation"])
OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", "./outputs")) / "generated"


class GenerationRequest(BaseModel):
    resume_id: int
    job_id: int


def _get_generation_inputs(db: Session, payload: GenerationRequest):
    resume = crud.get_resume(db, payload.resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    job = crud.get_job_description(db, payload.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job description not found")
    if not resume.parsed_text:
        raise HTTPException(status_code=400, detail="Resume has no parsed text")
    if not job.raw_text:
        raise HTTPException(status_code=400, detail="Job description has no text")
    return resume, job


def _basename(prefix: str, resume_id: int, job_id: int) -> str:
    return f"{prefix}_{resume_id}_{job_id}_{uuid.uuid4().hex[:8]}"


def _serialize_document(document) -> dict:
    return {
        "id": document.id,
        "resume_id": document.resume_id,
        "job_id": document.job_id,
        "doc_type": document.doc_type,
        "content_text": document.content_text,
        "match_score": document.match_score,
        "file_path": document.file_path,
        "prompt_version": document.prompt_version,
        "created_at": document.created_at,
    }


def _log_generation(
    *,
    run_name: str,
    payload: GenerationRequest,
    output_text: str,
) -> str | None:
    try:
        return log_generation_run(
            run_name=run_name,
            prompt_template_version="v1",
            job_id=payload.job_id,
            resume_id=payload.resume_id,
            prompt_used=f"{run_name} for resume_id={payload.resume_id}, job_id={payload.job_id}",
            output_text=output_text,
        )
    except Exception:
        # MLflow is optional for local generation; the document remains usable.
        return None


@router.post("/cover-letter", status_code=201)
def generate_cover_letter_endpoint(
    payload: GenerationRequest, db: Session = Depends(get_db)
) -> dict:
    resume, job = _get_generation_inputs(db, payload)
    result = generate_and_compile_cover_letter(
        resume.parsed_text,
        job.raw_text,
        job.company,
        job.role,
        str(OUTPUTS_DIR),
        _basename("cover_letter", resume.id, job.id),
    )
    if not result["success"]:
        raise HTTPException(status_code=502, detail=result["error"] or "Cover letter compilation failed")

    prompt_version = _log_generation(
        run_name="cover_letter",
        payload=payload,
        output_text=result["latex_source"],
    )
    latex_document = crud.create_generated_document(
        db,
        resume_id=resume.id,
        job_id=job.id,
        doc_type="cover_letter_latex",
        content_text=result["latex_source"],
        prompt_version=prompt_version,
    )
    pdf_document = crud.create_generated_document(
        db,
        resume_id=resume.id,
        job_id=job.id,
        doc_type="cover_letter_pdf",
        file_path=result["pdf_path"],
        prompt_version=prompt_version,
    )
    return {
        "success": True,
        "attempts": result["attempts"],
        "documents": [_serialize_document(latex_document), _serialize_document(pdf_document)],
    }


@router.post("/tailor-cv", status_code=201)
def tailor_cv_endpoint(
    payload: GenerationRequest, db: Session = Depends(get_db)
) -> dict:
    resume, job = _get_generation_inputs(db, payload)
    template_path = Path(os.getenv("TEMPLATES_DIR", "./templates")) / "cv_template.tex"
    if not template_path.exists():
        raise HTTPException(status_code=400, detail="CV template not found")

    result = tailor_and_compile_cv(
        resume.parsed_text,
        job.raw_text,
        template_path.read_text(encoding="utf-8"),
        str(OUTPUTS_DIR),
        _basename("cv", resume.id, job.id),
    )
    if not result["success"]:
        raise HTTPException(status_code=502, detail=result["error"] or "CV compilation failed")

    prompt_version = _log_generation(
        run_name="cv_tailoring",
        payload=payload,
        output_text=result["latex_source"],
    )
    latex_document = crud.create_generated_document(
        db,
        resume_id=resume.id,
        job_id=job.id,
        doc_type="cv_latex",
        content_text=result["latex_source"],
        prompt_version=prompt_version,
    )
    pdf_document = crud.create_generated_document(
        db,
        resume_id=resume.id,
        job_id=job.id,
        doc_type="cv_pdf",
        file_path=result["pdf_path"],
        prompt_version=prompt_version,
    )
    return {
        "success": True,
        "attempts": result["attempts"],
        "documents": [_serialize_document(latex_document), _serialize_document(pdf_document)],
    }


@router.post("/score", status_code=201)
def score_endpoint(payload: GenerationRequest, db: Session = Depends(get_db)) -> dict:
    resume, job = _get_generation_inputs(db, payload)
    result = score_match(resume.parsed_text, job.raw_text)
    prompt_version = _log_generation(
        run_name="score_match",
        payload=payload,
        output_text=result["gap_analysis"],
    )
    document = crud.create_generated_document(
        db,
        resume_id=resume.id,
        job_id=job.id,
        doc_type="score",
        content_text=result["gap_analysis"],
        match_score=result["match_score"],
        prompt_version=prompt_version,
    )
    return {
        "match_score": result["match_score"],
        "gap_analysis": result["gap_analysis"],
        "document": _serialize_document(document),
    }
