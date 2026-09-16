import os
import uuid
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from src.database import crud
from src.document_processing.jd_parser import parse_job_description
from src.llm.cover_letter import generate_and_compile_cover_letter
from src.llm.cv_tailoring import tailor_and_compile_cv
from src.llm.scoring import score_match

OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", "./outputs")) / "generated"
ApplicationStatus = Literal[
    "Applied",
    "Interview Scheduled",
    "Interview Done",
    "Offer",
    "Rejected",
    "Ghosted",
]


def _source_records(db: Session, resume_id: int, job_id: int):
    resume = crud.get_resume(db, resume_id)
    job = crud.get_job_description(db, job_id)
    if resume is None or job is None:
        return None, None, {"success": False, "error": "Resume or job description not found"}
    if not resume.parsed_text or not job.raw_text:
        return None, None, {"success": False, "error": "Resume or job description has no text"}
    return resume, job, None


def _document(document) -> dict:
    return {
        "id": document.id,
        "resume_id": document.resume_id,
        "job_id": document.job_id,
        "doc_type": document.doc_type,
        "content_text": document.content_text,
        "match_score": document.match_score,
        "file_path": document.file_path,
        "prompt_version": document.prompt_version,
    }


def _basename(prefix: str, resume_id: int, job_id: int) -> str:
    return f"{prefix}_{resume_id}_{job_id}_{uuid.uuid4().hex[:8]}"


def create_job_description_tool(
    db: Session,
    company: str,
    role: str,
    raw_text: str,
    url: str | None = None,
) -> dict:
    """Save a pasted job description so later agent tools can use its ID."""
    company = company.strip()
    role = role.strip()
    raw_text = parse_job_description(raw_text=raw_text)
    if not company or not role:
        return {"success": False, "error": "Company and role are required"}
    if not raw_text:
        return {"success": False, "error": "Job description text is required"}

    job = crud.create_job_description(
        db,
        company=company,
        role=role,
        raw_text=raw_text,
        url=url,
    )
    return {
        "success": True,
        "job": {
            "id": job.id,
            "company": job.company,
            "role": job.role,
            "url": job.url,
        },
    }


def find_job_descriptions_tool(
    db: Session,
    company: str | None = None,
    role: str | None = None,
) -> dict:
    """Find saved job descriptions using case-insensitive company/role matching."""
    company_query = company.strip().lower() if company else None
    role_query = role.strip().lower() if role else None
    if not company_query and not role_query:
        return {"success": False, "error": "Company or role is required"}

    matches = []
    for job in crud.list_job_descriptions(db):
        if company_query and company_query not in job.company.lower():
            continue
        if role_query and role_query not in job.role.lower():
            continue
        matches.append(
            {
                "id": job.id,
                "company": job.company,
                "role": job.role,
                "url": job.url,
                "upload_date": job.upload_date,
            }
        )

    return {"success": True, "matches": matches, "count": len(matches)}


def generate_cover_letter_tool(db: Session, resume_id: int, job_id: int) -> dict:
    resume, job, error = _source_records(db, resume_id, job_id)
    if error:
        return error
    result = generate_and_compile_cover_letter(
        resume.parsed_text,
        job.raw_text,
        job.company,
        job.role,
        str(OUTPUTS_DIR),
        _basename("cover_letter", resume_id, job_id),
    )
    if not result["success"]:
        return {"success": False, "error": result["error"] or "Cover letter compilation failed"}

    latex = crud.create_generated_document(
        db,
        resume_id=resume_id,
        job_id=job_id,
        doc_type="cover_letter_latex",
        content_text=result["latex_source"],
    )
    pdf = crud.create_generated_document(
        db,
        resume_id=resume_id,
        job_id=job_id,
        doc_type="cover_letter_pdf",
        file_path=result["pdf_path"],
    )
    return {"success": True, "attempts": result["attempts"], "documents": [_document(latex), _document(pdf)]}


def tailor_cv_tool(db: Session, resume_id: int, job_id: int) -> dict:
    resume, job, error = _source_records(db, resume_id, job_id)
    if error:
        return error
    template_path = Path(os.getenv("TEMPLATES_DIR", "./templates")) / "cv_template.tex"
    if not template_path.exists():
        return {"success": False, "error": "CV template not found"}

    result = tailor_and_compile_cv(
        resume.parsed_text,
        job.raw_text,
        template_path.read_text(encoding="utf-8"),
        str(OUTPUTS_DIR),
        _basename("cv", resume_id, job_id),
    )
    if not result["success"]:
        return {"success": False, "error": result["error"] or "CV compilation failed"}

    latex = crud.create_generated_document(
        db,
        resume_id=resume_id,
        job_id=job_id,
        doc_type="cv_latex",
        content_text=result["latex_source"],
    )
    pdf = crud.create_generated_document(
        db,
        resume_id=resume_id,
        job_id=job_id,
        doc_type="cv_pdf",
        file_path=result["pdf_path"],
    )
    return {"success": True, "attempts": result["attempts"], "documents": [_document(latex), _document(pdf)]}


def score_match_tool(db: Session, resume_id: int, job_id: int) -> dict:
    resume, job, error = _source_records(db, resume_id, job_id)
    if error:
        return error
    result = score_match(resume.parsed_text, job.raw_text)
    document = crud.create_generated_document(
        db,
        resume_id=resume_id,
        job_id=job_id,
        doc_type="score",
        content_text=result["gap_analysis"],
        match_score=result["match_score"],
    )
    return {
        "success": True,
        "match_score": result["match_score"],
        "gap_analysis": result["gap_analysis"],
        "document": _document(document),
    }


def get_application_tool(db: Session, application_id: int) -> dict:
    application = crud.get_application(db, application_id)
    if application is None:
        return {"success": False, "error": "Application not found"}
    return {
        "success": True,
        "application": {
            "id": application.id,
            "resume_id": application.resume_id,
            "job_id": application.job_id,
            "status": application.status,
            "match_score": application.match_score,
            "notes": application.notes,
            "submitted_at": application.submitted_at,
        },
        "documents": [_document(document) for document in application.documents],
    }


def update_status_tool(
    db: Session,
    application_id: int,
    status: ApplicationStatus,
    notes: str | None = None,
) -> dict:
    application = crud.update_application(db, application_id, status=status, notes=notes)
    if application is None:
        return {"success": False, "error": "Application not found"}
    return {"success": True, "application_id": application.id, "status": application.status}


def list_applications_tool(
    db: Session,
    status: ApplicationStatus | None = None,
    company: str | None = None,
    min_score: float | None = None,
) -> dict:
    applications = crud.list_applications(db, status=status, company=company, min_score=min_score)
    return {
        "success": True,
        "applications": [
            {
                "id": application.id,
                "resume_id": application.resume_id,
                "job_id": application.job_id,
                "status": application.status,
                "match_score": application.match_score,
                "notes": application.notes,
            }
            for application in applications
        ],
    }


def search_applications_tool(db: Session, query: str) -> dict:
    applications = crud.list_applications(db, company=query)
    return {
        "success": True,
        "query": query,
        "applications": [
            {
                "id": application.id,
                "job_id": application.job_id,
                "status": application.status,
                "match_score": application.match_score,
            }
            for application in applications
        ],
    }


def parse_emails_tool(db: Session) -> dict:
    del db
    return {"success": False, "error": "Email sync is not configured yet"}
