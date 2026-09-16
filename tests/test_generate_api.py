import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.database.connection as connection
from api.main import app
from api.routers import generate
from src.database import crud


@pytest.fixture()
def client(tmp_path, monkeypatch):
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(connection, "engine", test_engine)
    monkeypatch.setattr(
        connection,
        "SessionLocal",
        sessionmaker(bind=test_engine, autoflush=False, autocommit=False),
    )
    monkeypatch.setattr(generate, "OUTPUTS_DIR", tmp_path / "generated")
    monkeypatch.setattr(generate, "_log_generation", lambda **kwargs: "run-123")
    with TestClient(app) as test_client:
        yield test_client


def _create_source_records():
    db = connection.SessionLocal()
    try:
        resume = crud.create_resume(db, "resume.pdf", "/tmp/resume.pdf", "Python engineer")
        job = crud.create_job_description(db, "Acme", "Backend Engineer", "Need Python.")
        return resume.id, job.id
    finally:
        db.close()


def test_generate_cover_letter_persists_latex_and_pdf_documents(client, monkeypatch, tmp_path):
    resume_id, job_id = _create_source_records()

    def fake_cover_letter(*args, **kwargs):
        return {
            "success": True,
            "latex_source": r"\documentclass{article}",
            "pdf_path": str(tmp_path / "cover_letter.pdf"),
            "attempts": 1,
            "error": None,
        }

    monkeypatch.setattr(generate, "generate_and_compile_cover_letter", fake_cover_letter)

    response = client.post(
        "/generate/cover-letter", json={"resume_id": resume_id, "job_id": job_id}
    )

    assert response.status_code == 201
    documents = response.json()["documents"]
    assert [document["doc_type"] for document in documents] == [
        "cover_letter_latex",
        "cover_letter_pdf",
    ]
    assert documents[0]["content_text"] == r"\documentclass{article}"
    assert documents[1]["file_path"].endswith("cover_letter.pdf")

    db = connection.SessionLocal()
    try:
        stored = crud.list_unlinked_documents_for_pair(db, resume_id, job_id)
        assert len(stored) == 2
        assert all(document.application_id is None for document in stored)
    finally:
        db.close()


def test_generate_cv_reads_template_and_persists_documents(client, monkeypatch, tmp_path):
    resume_id, job_id = _create_source_records()
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "cv_template.tex").write_text("template", encoding="utf-8")
    monkeypatch.setenv("TEMPLATES_DIR", str(template_dir))

    captured = {}

    def fake_cv(*args, **kwargs):
        captured["template"] = args[2]
        return {
            "success": True,
            "latex_source": "cv latex",
            "pdf_path": str(tmp_path / "cv.pdf"),
            "attempts": 1,
            "error": None,
        }

    monkeypatch.setattr(generate, "tailor_and_compile_cv", fake_cv)

    response = client.post(
        "/generate/tailor-cv", json={"resume_id": resume_id, "job_id": job_id}
    )

    assert response.status_code == 201
    assert captured["template"] == "template"
    assert [document["doc_type"] for document in response.json()["documents"]] == [
        "cv_latex",
        "cv_pdf",
    ]


def test_generate_score_persists_normalized_score_document(client, monkeypatch):
    resume_id, job_id = _create_source_records()
    monkeypatch.setattr(
        generate,
        "score_match",
        lambda *args, **kwargs: {
            "match_score": 0.85,
            "gap_analysis": "Needs more distributed systems experience.",
        },
    )

    response = client.post("/generate/score", json={"resume_id": resume_id, "job_id": job_id})

    assert response.status_code == 201
    assert response.json()["match_score"] == 0.85
    assert response.json()["document"]["doc_type"] == "score"
    assert response.json()["document"]["match_score"] == 0.85


def test_generation_validates_source_records(client):
    response = client.post("/generate/score", json={"resume_id": 999, "job_id": 999})

    assert response.status_code == 404
    assert response.json()["detail"] == "Resume not found"


def test_generation_rejects_missing_source_text(client):
    db = connection.SessionLocal()
    try:
        resume = crud.create_resume(db, "resume.pdf", "/tmp/resume.pdf")
        job = crud.create_job_description(db, "Acme", "Backend Engineer", "Need Python.")
        resume_id, job_id = resume.id, job.id
    finally:
        db.close()

    response = client.post("/generate/score", json={"resume_id": resume_id, "job_id": job_id})

    assert response.status_code == 400
    assert response.json()["detail"] == "Resume has no parsed text"
