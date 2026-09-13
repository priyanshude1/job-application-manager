import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database import crud
from src.database.connection import get_db
from src.document_processing.jd_parser import parse_job_description
from src.document_processing.resume_parser import parse_resume_pdf

router = APIRouter()

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
RESUMES_DIR = DATA_DIR / "resumes"
JOB_DESCRIPTIONS_DIR = DATA_DIR / "job_descriptions"


def _save_upload(file: UploadFile, directory: Path) -> str:
    """Write an uploaded PDF to disk under a collision-proof name.

    Rejects anything that isn't a .pdf, since both parsers assume a valid
    PDF and would otherwise fail deep inside PyMuPDF with a confusing error
    instead of a clear 400 at the boundary where the bad input entered.
    """
    if file.filename is None or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")

    directory.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
    destination = directory / unique_name

    with destination.open("wb") as out_file:
        out_file.write(file.file.read())

    return str(destination)


@router.post("/resume/upload")
def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    file_path = _save_upload(file, RESUMES_DIR)
    parsed_text = parse_resume_pdf(file_path)
    resume = crud.create_resume(db, filename=file.filename, file_path=file_path, parsed_text=parsed_text)
    return {"id": resume.id, "filename": resume.filename, "file_path": resume.file_path}


@router.post("/jobs/upload")
def upload_job_description(
    file: UploadFile = File(...),
    company: str = Form(...),
    role: str = Form(...),
    url: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    file_path = _save_upload(file, JOB_DESCRIPTIONS_DIR)
    raw_text = parse_job_description(file_path=file_path)
    job = crud.create_job_description(
        db, company=company, role=role, raw_text=raw_text, file_path=file_path, url=url
    )
    return {"id": job.id, "company": job.company, "role": job.role}


class JobDescriptionPaste(BaseModel):
    company: str
    role: str
    raw_text: str
    url: str | None = None


@router.post("/jobs/paste")
def paste_job_description(payload: JobDescriptionPaste, db: Session = Depends(get_db)) -> dict:
    raw_text = parse_job_description(raw_text=payload.raw_text)
    job = crud.create_job_description(db, company=payload.company, role=payload.role, raw_text=raw_text, url=payload.url)
    return {"id": job.id, "company": job.company, "role": job.role}
