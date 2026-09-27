import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.database.connection as connection
from api.main import app
from src.agent import tools
from src.database import crud


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Same real-file-per-test isolation as test_application_api.py -- a relative
    # sqlite:// URL resolves to an absolute path once, at create_engine() time,
    # not dynamically per connection, so chdir() alone would not isolate this.
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(connection, "engine", test_engine)
    monkeypatch.setattr(
        connection, "SessionLocal", sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    )
    with TestClient(app) as test_client:
        yield test_client


def _create_application(client):
    db = connection.SessionLocal()
    try:
        resume = crud.create_resume(db, "resume.pdf", "/tmp/resume.pdf", "Python engineer")
        job = crud.create_job_description(db, "Acme", "Backend Engineer", "Need Python.")
        application = crud.create_application(db, resume_id=resume.id, job_id=job.id, submission_method="manual")
        return application.id
    finally:
        db.close()


def test_sync_emails_endpoint_delegates_to_parse_emails_tool(client, monkeypatch):
    calls = []

    def fake_parse_emails_tool(db):
        calls.append(db)
        return {"success": True, "processed": 2, "events": [], "errors": []}

    monkeypatch.setattr(tools, "parse_emails_tool", fake_parse_emails_tool)

    response = client.post("/emails/sync")

    assert response.status_code == 200
    assert response.json() == {"success": True, "processed": 2, "events": [], "errors": []}
    assert len(calls) == 1


def test_sync_emails_endpoint_returns_502_on_auth_failure(client, monkeypatch):
    def failing_parse_emails_tool(db):
        return {"success": False, "error": "Gmail OAuth client secret not found"}

    monkeypatch.setattr(tools, "parse_emails_tool", failing_parse_emails_tool)

    response = client.post("/emails/sync")

    assert response.status_code == 502
    assert response.json()["detail"] == "Gmail OAuth client secret not found"


def test_list_email_events_returns_404_for_missing_application(client):
    response = client.get("/emails/999")
    assert response.status_code == 404


def test_list_email_events_returns_events_for_application(client):
    application_id = _create_application(client)

    db = connection.SessionLocal()
    try:
        crud.create_email_event(
            db,
            raw_email_id="email-1",
            application_id=application_id,
            subject="Interview invite",
            snippet="We would like to schedule an interview",
            detected_intent="interview_invite",
            status_change="Interview Scheduled",
        )
    finally:
        db.close()

    response = client.get(f"/emails/{application_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["application_id"] == application_id
    assert len(body["events"]) == 1
    assert body["events"][0]["detected_intent"] == "interview_invite"
    assert body["events"][0]["status_change"] == "Interview Scheduled"
