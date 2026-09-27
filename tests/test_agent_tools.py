from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.agent import tools
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


def _fake_fetch(emails_by_company, calls):
    def fetch(service, *, company_names, days=7, max_results=50):
        calls.append(company_names)
        return emails_by_company.get(company_names[0], [])

    return fetch


def _fake_classify(intent_by_subject, calls):
    def classify(subject, snippet, *, client=None):
        calls.append(subject)
        return intent_by_subject.get(subject, "unknown")

    return classify


def test_parse_emails_updates_status_from_interview_invite(db, monkeypatch):
    resume = crud.create_resume(db, filename="r.pdf", file_path="/r.pdf", parsed_text="text")
    job = crud.create_job_description(db, company="Acme", role="Backend Engineer", raw_text="text")
    application = crud.create_application(db, resume_id=resume.id, job_id=job.id, submission_method="manual")

    fetch_calls, classify_calls = [], []
    monkeypatch.setattr(
        tools,
        "fetch_recent_emails",
        _fake_fetch(
            {
                "Acme": [
                    {
                        "raw_email_id": "email-1",
                        "subject": "Interview invite",
                        "from": "recruiting@acme.com",
                        "received_at": datetime(2026, 9, 20, tzinfo=timezone.utc),
                        "snippet": "We would like to schedule an interview",
                    }
                ]
            },
            fetch_calls,
        ),
    )
    monkeypatch.setattr(
        tools, "classify_email_intent", _fake_classify({"Interview invite": "interview_invite"}, classify_calls)
    )

    result = tools.parse_emails_tool(db, service=object(), days=7)

    assert result["success"] is True
    assert result["processed"] == 1
    assert result["errors"] == []
    assert fetch_calls == [["Acme"]]

    db.refresh(application)
    assert application.status == "Interview Scheduled"

    events = crud.list_email_events_for_application(db, application.id)
    assert len(events) == 1
    assert events[0].detected_intent == "interview_invite"
    assert events[0].status_change == "Interview Scheduled"


def test_parse_emails_sets_confirmation_fields_without_touching_status(db, monkeypatch):
    resume = crud.create_resume(db, filename="r.pdf", file_path="/r.pdf", parsed_text="text")
    job = crud.create_job_description(db, company="Acme", role="Backend Engineer", raw_text="text")
    application = crud.create_application(db, resume_id=resume.id, job_id=job.id, submission_method="manual")
    original_status = application.status

    monkeypatch.setattr(
        tools,
        "fetch_recent_emails",
        _fake_fetch(
            {
                "Acme": [
                    {
                        "raw_email_id": "email-1",
                        "subject": "Application received",
                        "from": "no-reply@acme.com",
                        "received_at": datetime(2026, 9, 20, tzinfo=timezone.utc),
                        "snippet": "We have received your application",
                    }
                ]
            },
            [],
        ),
    )
    monkeypatch.setattr(
        tools, "classify_email_intent", _fake_classify({"Application received": "submission_confirmation"}, [])
    )

    result = tools.parse_emails_tool(db, service=object())
    assert result["processed"] == 1

    db.refresh(application)
    assert application.status == original_status  # unchanged -- confirmation is decoupled from status
    assert application.confirmed_at is not None
    assert application.confirmation_source == "email"


def test_parse_emails_dedups_before_reclassifying(db, monkeypatch):
    resume = crud.create_resume(db, filename="r.pdf", file_path="/r.pdf", parsed_text="text")
    job = crud.create_job_description(db, company="Acme", role="Backend Engineer", raw_text="text")
    crud.create_application(db, resume_id=resume.id, job_id=job.id, submission_method="manual")

    classify_calls = []
    email = {
        "raw_email_id": "email-1",
        "subject": "Interview invite",
        "from": "recruiting@acme.com",
        "received_at": datetime(2026, 9, 20, tzinfo=timezone.utc),
        "snippet": "We would like to schedule an interview",
    }
    monkeypatch.setattr(tools, "fetch_recent_emails", _fake_fetch({"Acme": [email]}, []))
    monkeypatch.setattr(
        tools, "classify_email_intent", _fake_classify({"Interview invite": "interview_invite"}, classify_calls)
    )

    first = tools.parse_emails_tool(db, service=object())
    second = tools.parse_emails_tool(db, service=object())

    assert first["processed"] == 1
    assert second["processed"] == 0
    assert len(classify_calls) == 1, "the second sync must skip classification entirely, not just skip the insert"


def test_parse_emails_logs_event_with_no_application_when_none_exists(db, monkeypatch):
    crud.create_job_description(db, company="Globex", role="SRE", raw_text="text")

    monkeypatch.setattr(
        tools,
        "fetch_recent_emails",
        _fake_fetch(
            {
                "Globex": [
                    {
                        "raw_email_id": "email-1",
                        "subject": "Rejection notice",
                        "from": "hr@globex.com",
                        "received_at": None,
                        "snippet": "We have decided not to move forward",
                    }
                ]
            },
            [],
        ),
    )
    monkeypatch.setattr(tools, "classify_email_intent", _fake_classify({"Rejection notice": "rejection"}, []))

    result = tools.parse_emails_tool(db, service=object())

    assert result["processed"] == 1
    event = result["events"][0]
    assert event["application_id"] is None
    assert event["detected_intent"] == "rejection"
    assert event["status_change"] is None


def test_parse_emails_returns_early_when_no_job_descriptions_saved(db):
    result = tools.parse_emails_tool(db, service=object())
    assert result == {"success": True, "processed": 0, "events": [], "errors": []}


def test_parse_emails_collects_per_company_errors_without_failing_whole_sync(db, monkeypatch):
    crud.create_job_description(db, company="Acme", role="Backend Engineer", raw_text="text")
    crud.create_job_description(db, company="Globex", role="SRE", raw_text="text")

    def flaky_fetch(service, *, company_names, days=7, max_results=50):
        if company_names[0] == "Acme":
            raise RuntimeError("Gmail API quota exceeded")
        return []

    monkeypatch.setattr(tools, "fetch_recent_emails", flaky_fetch)

    result = tools.parse_emails_tool(db, service=object())

    assert result["success"] is True
    assert result["errors"] == [{"company": "Acme", "error": "Gmail API quota exceeded"}]


def test_parse_emails_reports_auth_failure_without_raising(db, monkeypatch):
    crud.create_job_description(db, company="Acme", role="Backend Engineer", raw_text="text")

    def failing_get_service():
        raise RuntimeError("Gmail OAuth client secret not found")

    monkeypatch.setattr(tools, "get_gmail_service", failing_get_service)

    result = tools.parse_emails_tool(db)

    assert result == {"success": False, "error": "Gmail OAuth client secret not found"}
