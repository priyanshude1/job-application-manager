from datetime import datetime

from sqlalchemy.orm import Session

from src.database.models import (
    Application,
    EmailEvent,
    GeneratedDocument,
    JobDescription,
    Resume,
    utcnow,
)

# --- Resumes ---


def create_resume(db: Session, filename: str, file_path: str, parsed_text: str | None = None) -> Resume:
    resume = Resume(filename=filename, file_path=file_path, parsed_text=parsed_text)
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


def get_resume(db: Session, resume_id: int) -> Resume | None:
    return db.get(Resume, resume_id)


def list_resumes(db: Session) -> list[Resume]:
    return list(db.query(Resume).order_by(Resume.upload_date.desc()).all())


# --- Job Descriptions ---


def create_job_description(
    db: Session,
    company: str,
    role: str,
    raw_text: str | None = None,
    file_path: str | None = None,
    url: str | None = None,
) -> JobDescription:
    job = JobDescription(company=company, role=role, raw_text=raw_text, file_path=file_path, url=url)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job_description(db: Session, job_id: int) -> JobDescription | None:
    return db.get(JobDescription, job_id)


def list_job_descriptions(db: Session) -> list[JobDescription]:
    return list(db.query(JobDescription).order_by(JobDescription.upload_date.desc()).all())


# --- Applications ---


def create_application(
    db: Session,
    resume_id: int,
    job_id: int,
    status: str = "Applied",
    date_applied: datetime | None = None,
    notes: str | None = None,
) -> Application:
    application = Application(
        resume_id=resume_id,
        job_id=job_id,
        status=status,
        date_applied=date_applied or utcnow(),
        notes=notes,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


def get_application(db: Session, application_id: int) -> Application | None:
    return db.get(Application, application_id)


def list_applications(
    db: Session, status: str | None = None, company: str | None = None
) -> list[Application]:
    query = db.query(Application)
    if status is not None:
        query = query.filter(Application.status == status)
    if company is not None:
        query = query.join(JobDescription).filter(JobDescription.company == company)
    return list(query.order_by(Application.created_at.desc()).all())


def update_application(
    db: Session,
    application_id: int,
    status: str | None = None,
    notes: str | None = None,
    match_score: float | None = None,
) -> Application | None:
    application = db.get(Application, application_id)
    if application is None:
        return None
    if status is not None:
        application.status = status
    if notes is not None:
        application.notes = notes
    if match_score is not None:
        application.match_score = match_score
    application.updated_at = utcnow()
    db.commit()
    db.refresh(application)
    return application


def delete_application(db: Session, application_id: int) -> bool:
    application = db.get(Application, application_id)
    if application is None:
        return False
    db.delete(application)
    db.commit()
    return True


# --- Generated Documents ---


def create_generated_document(
    db: Session,
    application_id: int,
    doc_type: str,
    content_text: str | None = None,
    file_path: str | None = None,
    prompt_version: str | None = None,
) -> GeneratedDocument:
    document = GeneratedDocument(
        application_id=application_id,
        doc_type=doc_type,
        content_text=content_text,
        file_path=file_path,
        prompt_version=prompt_version,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def list_documents_for_application(db: Session, application_id: int) -> list[GeneratedDocument]:
    return list(
        db.query(GeneratedDocument)
        .filter(GeneratedDocument.application_id == application_id)
        .order_by(GeneratedDocument.created_at.desc())
        .all()
    )


# --- Email Events ---


def create_email_event(
    db: Session,
    raw_email_id: str,
    application_id: int | None = None,
    subject: str | None = None,
    snippet: str | None = None,
    detected_intent: str | None = None,
    status_change: str | None = None,
) -> EmailEvent | None:
    existing = db.query(EmailEvent).filter(EmailEvent.raw_email_id == raw_email_id).first()
    if existing is not None:
        return None
    event = EmailEvent(
        raw_email_id=raw_email_id,
        application_id=application_id,
        subject=subject,
        snippet=snippet,
        detected_intent=detected_intent,
        status_change=status_change,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_email_events_for_application(db: Session, application_id: int) -> list[EmailEvent]:
    return list(
        db.query(EmailEvent)
        .filter(EmailEvent.application_id == application_id)
        .order_by(EmailEvent.received_at.desc())
        .all()
    )
