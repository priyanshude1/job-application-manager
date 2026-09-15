from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database import crud
from src.database.connection import get_db

ApplicationStatus = Literal[
    "Applied",
    "Interview Scheduled",
    "Interview Done",
    "Offer",
    "Rejected",
    "Ghosted",
]

router = APIRouter(prefix="/applications", tags=["applications"])


class ApplicationCreate(BaseModel):
    resume_id: int
    job_id: int
    submission_method: Literal["manual", "automatic"]
    date_applied: datetime | None = None
    notes: str | None = None


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = None
    match_score: float | None = Field(default=None, ge=0.0, le=1.0)


def _serialize_application(application, include_documents: bool = False) -> dict:
    result = {
        "id": application.id,
        "resume_id": application.resume_id,
        "job_id": application.job_id,
        "submission_method": application.submission_method,
        "date_applied": application.date_applied,
        "status": application.status,
        "match_score": application.match_score,
        "notes": application.notes,
    }
    if include_documents:
        result["documents"] = [
            {
                "id": document.id,
                "doc_type": document.doc_type,
                "content_text": document.content_text,
                "file_path": document.file_path,
                "prompt_version": document.prompt_version,
                "created_at": document.created_at,
            }
            for document in application.documents
        ]
    return result


@router.post("", status_code=201)
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db)) -> dict:
    if crud.get_resume(db, payload.resume_id) is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    if crud.get_job_description(db, payload.job_id) is None:
        raise HTTPException(status_code=404, detail="Job description not found")

    application = crud.create_application(
        db,
        resume_id=payload.resume_id,
        job_id=payload.job_id,
        submission_method=payload.submission_method,
        date_applied=payload.date_applied,
        notes=payload.notes,
    )
    return _serialize_application(application)


@router.get("")
def list_applications(
    status: ApplicationStatus | None = None,
    company: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    applications = crud.list_applications(db, status=status, company=company)
    return [_serialize_application(application) for application in applications]


@router.get("/{application_id}")
def get_application(application_id: int, db: Session = Depends(get_db)) -> dict:
    application = crud.get_application(db, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return _serialize_application(application, include_documents=True)


@router.patch("/{application_id}")
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
) -> dict:
    application = crud.update_application(
        db,
        application_id,
        **payload.model_dump(exclude_unset=True),
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return _serialize_application(application)


@router.delete("/{application_id}")
def delete_application(application_id: int, db: Session = Depends(get_db)) -> dict:
    if not crud.delete_application(db, application_id):
        raise HTTPException(status_code=404, detail="Application not found")
    return {"deleted": True, "application_id": application_id}