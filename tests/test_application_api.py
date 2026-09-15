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
    assert created.json()["submitted_at"] is not None
    assert created.json()["confirmed_at"] is None

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


def test_patch_nonexistent_application_returns_404(client):
    response = client.patch("/applications/999", json={"status": "Offer"})
    assert response.status_code == 404


def test_delete_nonexistent_application_returns_404(client):
    response = client.delete("/applications/999")
    assert response.status_code == 404


def test_confirm_application_endpoint(client):
    resume_id, job_id = _create_source_records(client)
    created = client.post(
        "/applications",
        json={"resume_id": resume_id, "job_id": job_id, "submission_method": "manual"},
    )
    application_id = created.json()["id"]

    confirmed = client.patch(
        f"/applications/{application_id}",
        json={"confirmed_at": "2026-09-16T10:00:00", "confirmation_source": "manual"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmed_at"] is not None
    assert confirmed.json()["confirmation_source"] == "manual"

    invalid_source = client.patch(
        f"/applications/{application_id}", json={"confirmation_source": "sms"}
    )
    assert invalid_source.status_code == 422


def test_list_applications_filters_by_min_score(client):
    resume_id, job_id = _create_source_records(client)
    created = client.post(
        "/applications",
        json={"resume_id": resume_id, "job_id": job_id, "submission_method": "manual"},
    )
    application_id = created.json()["id"]
    client.patch(f"/applications/{application_id}", json={"match_score": 0.8})

    hit = client.get("/applications", params={"min_score": 0.7})
    miss = client.get("/applications", params={"min_score": 0.9})
    assert len(hit.json()) == 1
    assert len(miss.json()) == 0


def test_application_creation_backfills_and_snapshots_score_document(client):
    resume_id, job_id = _create_source_records(client)

    db = SessionLocal()
    try:
        crud.create_generated_document(
            db, resume_id=resume_id, job_id=job_id, doc_type="score",
            match_score=0.9, content_text="Strong match overall.",
        )
    finally:
        db.close()

    created = client.post(
        "/applications",
        json={"resume_id": resume_id, "job_id": job_id, "submission_method": "manual"},
    )
    assert created.status_code == 201
    assert created.json()["match_score"] == 0.9

    fetched = client.get(f"/applications/{created.json()['id']}")
    documents = fetched.json()["documents"]
    assert len(documents) == 1
    assert documents[0]["doc_type"] == "score"
    assert documents[0]["match_score"] == 0.9