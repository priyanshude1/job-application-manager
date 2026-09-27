import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.database.connection as connection
from api.main import app
from src.database import crud


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(connection, "engine", test_engine)
    monkeypatch.setattr(
        connection, "SessionLocal", sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    )
    with TestClient(app) as test_client:
        yield test_client


def test_list_resumes_returns_uploaded_resumes(client):
    db = connection.SessionLocal()
    try:
        crud.create_resume(db, "resume.pdf", "/tmp/resume.pdf", "Python engineer")
    finally:
        db.close()

    response = client.get("/resumes")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["filename"] == "resume.pdf"


def test_list_resumes_empty_when_none_uploaded(client):
    response = client.get("/resumes")
    assert response.status_code == 200
    assert response.json() == []


def test_list_jobs_returns_saved_job_descriptions(client):
    db = connection.SessionLocal()
    try:
        crud.create_job_description(db, "Acme", "Backend Engineer", "Need Python.")
    finally:
        db.close()

    response = client.get("/jobs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["company"] == "Acme"
    assert body[0]["role"] == "Backend Engineer"
