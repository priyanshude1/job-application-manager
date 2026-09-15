import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import crud
from src.database.models import Base


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_create_and_get_resume(db):
    resume = crud.create_resume(db, filename="resume.pdf", file_path="/data/resumes/resume.pdf")
    fetched = crud.get_resume(db, resume.id)
    assert fetched is not None
    assert fetched.filename == "resume.pdf"


def test_create_job_description(db):
    job = crud.create_job_description(db, company="Acme", role="Backend Engineer", raw_text="...")
    assert job.id is not None
    assert job.company == "Acme"


def test_application_lifecycle(db):
    resume = crud.create_resume(db, filename="r.pdf", file_path="/data/resumes/r.pdf")
    job = crud.create_job_description(db, company="Acme", role="Backend Engineer")

    application = crud.create_application(
        db, resume_id=resume.id, job_id=job.id, submission_method="manual"
    )
    assert application.status == "Applied"

    updated = crud.update_application(db, application.id, status="Interview Scheduled")
    assert updated.status == "Interview Scheduled"

    applications = crud.list_applications(db, status="Interview Scheduled")
    assert len(applications) == 1

    deleted = crud.delete_application(db, application.id)
    assert deleted is True
    assert crud.get_application(db, application.id) is None


def test_application_cascade_deletes_documents(db):
    resume = crud.create_resume(db, filename="r.pdf", file_path="/data/resumes/r.pdf")
    job = crud.create_job_description(db, company="Acme", role="Backend Engineer")
    application = crud.create_application(
        db, resume_id=resume.id, job_id=job.id, submission_method="automatic"
    )

    crud.create_generated_document(db, application_id=application.id, doc_type="cover_letter")
    assert len(crud.list_documents_for_application(db, application.id)) == 1

    crud.delete_application(db, application.id)
    assert crud.list_documents_for_application(db, application.id) == []


def test_email_event_deduplication(db):
    resume = crud.create_resume(db, filename="r.pdf", file_path="/data/resumes/r.pdf")
    job = crud.create_job_description(db, company="Acme", role="Backend Engineer")
    application = crud.create_application(
        db, resume_id=resume.id, job_id=job.id, submission_method="manual"
    )

    first = crud.create_email_event(
        db, raw_email_id="msg-1", application_id=application.id, detected_intent="interview_invite"
    )
    assert first is not None

    duplicate = crud.create_email_event(
        db, raw_email_id="msg-1", application_id=application.id, detected_intent="interview_invite"
    )
    assert duplicate is None

    events = crud.list_email_events_for_application(db, application.id)
    assert len(events) == 1
