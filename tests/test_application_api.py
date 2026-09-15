import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.database import crud
from src.database.connection import SessionLocal


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def _create_source_records(client):
    db = SessionLocal()
    try:
        resume = crud.create_resume(db, "resume.pdf", "/tmp/resume.pdf", "Python engineer")
        job = crud.create_job_description(db, "Acme", "Backend Engineer", "Need Python.")
        return resume.id, job.id
    finally:
        db.close()


def test_application_crud_endpoints(client):
    resume_id, job_id = _create_source_records(client)

    created = client.post(
        "/applications",
        json={
            "resume_id": resume_id,
            "job_id": job_id,
            "submission_method": "manual",
            "notes": "Follow up next week",
        },
    )
    assert created.status_code == 201
    application_id = created.json()["id"]
    assert created.json()["status"] == "Applied"
    assert created.json()["submission_method"] == "manual"

    listed = client.get("/applications?company=Acme")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    updated = client.patch(
        f"/applications/{application_id}",
        json={"status": "Interview Scheduled", "match_score": 0.8},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "Interview Scheduled"
    assert updated.json()["match_score"] == 0.8

    fetched = client.get(f"/applications/{application_id}")
    assert fetched.status_code == 200
    assert fetched.json()["documents"] == []

    deleted = client.delete(f"/applications/{application_id}")
    assert deleted.status_code == 200
    assert client.get(f"/applications/{application_id}").status_code == 404


def test_application_api_validates_references_and_fields(client):
    missing_method = client.post("/applications", json={"resume_id": 999, "job_id": 999})
    assert missing_method.status_code == 422

    missing_reference = client.post(
        "/applications",
        json={"resume_id": 999, "job_id": 999, "submission_method": "automatic"},
    )
    assert missing_reference.status_code == 404

    invalid_score = client.patch("/applications/999", json={"match_score": 1.1})
    assert invalid_score.status_code == 422

    invalid_status = client.patch("/applications/999", json={"status": "Unknown"})
    assert invalid_status.status_code == 422