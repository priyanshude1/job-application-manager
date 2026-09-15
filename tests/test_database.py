from datetime import datetime

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
    assert application.submitted_at is not None
    assert application.confirmed_at is None
    assert application.confirmation_source is None
    assert application.match_score is None

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

    crud.create_generated_document(
        db, resume_id=resume.id, job_id=job.id, doc_type="cover_letter",
        application_id=application.id,
    )
    assert len(crud.list_documents_for_application(db, application.id)) == 1

    crud.delete_application(db, application.id)
    assert crud.list_documents_for_application(db, application.id) == []


def test_create_application_copies_match_score_from_latest_score_document(db):
    resume = crud.create_resume(db, filename="r.pdf", file_path="/data/resumes/r.pdf")
    job = crud.create_job_description(db, company="Acme", role="Backend Engineer")

    crud.create_generated_document(
        db, resume_id=resume.id, job_id=job.id, doc_type="score",
        match_score=0.6, content_text="First pass.",
    )
    crud.create_generated_document(
        db, resume_id=resume.id, job_id=job.id, doc_type="score",
        match_score=0.83, content_text="Re-scored after tailoring.",
    )

    application = crud.create_application(
        db, resume_id=resume.id, job_id=job.id, submission_method="manual"
    )
    assert application.match_score == 0.83


def test_create_application_backfills_unlinked_generated_documents(db):
    resume = crud.create_resume(db, filename="r.pdf", file_path="/data/resumes/r.pdf")
    job = crud.create_job_description(db, company="Acme", role="Backend Engineer")

    cover_letter = crud.create_generated_document(
        db, resume_id=resume.id, job_id=job.id, doc_type="cover_letter", content_text="Dear..."
    )
    assert cover_letter.application_id is None

    application = crud.create_application(
        db, resume_id=resume.id, job_id=job.id, submission_method="manual"
    )

    db.refresh(cover_letter)
    assert cover_letter.application_id == application.id


def test_list_unlinked_documents_for_pair(db):
    resume = crud.create_resume(db, filename="r.pdf", file_path="/data/resumes/r.pdf")
    job_a = crud.create_job_description(db, company="Acme", role="Backend Engineer")
    job_b = crud.create_job_description(db, company="Globex", role="Data Engineer")

    unlinked = crud.create_generated_document(
        db, resume_id=resume.id, job_id=job_a.id, doc_type="cover_letter"
    )

    assert crud.list_unlinked_documents_for_pair(db, resume.id, job_a.id) == [unlinked]
    assert crud.list_unlinked_documents_for_pair(db, resume.id, job_b.id) == []

    crud.create_application(db, resume_id=resume.id, job_id=job_a.id, submission_method="manual")
    assert crud.list_unlinked_documents_for_pair(db, resume.id, job_a.id) == []


def test_list_applications_filters_by_min_score(db):
    resume = crud.create_resume(db, filename="r.pdf", file_path="/data/resumes/r.pdf")
    job = crud.create_job_description(db, company="Acme", role="Backend Engineer")

    low = crud.create_application(db, resume_id=resume.id, job_id=job.id, submission_method="manual")
    crud.update_application(db, low.id, match_score=0.4)
    high = crud.create_application(db, resume_id=resume.id, job_id=job.id, submission_method="manual")
    crud.update_application(db, high.id, match_score=0.9)

    results = crud.list_applications(db, min_score=0.8)
    assert [application.id for application in results] == [high.id]


def test_update_application_sets_confirmation_fields(db):
    resume = crud.create_resume(db, filename="r.pdf", file_path="/data/resumes/r.pdf")
    job = crud.create_job_description(db, company="Acme", role="Backend Engineer")
    application = crud.create_application(
        db, resume_id=resume.id, job_id=job.id, submission_method="manual"
    )

    confirmed_at = datetime(2026, 9, 16, 10, 0, 0)
    updated = crud.update_application(
        db, application.id, confirmed_at=confirmed_at, confirmation_source="manual"
    )
    assert updated.confirmed_at == confirmed_at
    assert updated.confirmation_source == "manual"


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
