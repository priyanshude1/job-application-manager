import fitz
import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.document_processing.jd_parser import parse_job_description
from src.document_processing.resume_parser import parse_resume_pdf


def _make_pdf(path: str, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


@pytest.fixture()
def sample_pdf(tmp_path):
    path = tmp_path / "sample.pdf"
    _make_pdf(str(path), "Priyanshu Kumar\nSoftware Engineer")
    return str(path)


def test_parse_resume_pdf_extracts_text(sample_pdf):
    text = parse_resume_pdf(sample_pdf)
    assert "Priyanshu Kumar" in text
    assert "Software Engineer" in text


def test_parse_job_description_from_raw_text():
    text = parse_job_description(raw_text="  Backend role at Acme.  ")
    assert text == "Backend role at Acme."


def test_parse_job_description_from_pdf(sample_pdf):
    text = parse_job_description(file_path=sample_pdf)
    assert "Priyanshu Kumar" in text


def test_parse_job_description_requires_one_input():
    with pytest.raises(ValueError):
        parse_job_description()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def test_upload_resume_endpoint(client, sample_pdf):
    with open(sample_pdf, "rb") as f:
        response = client.post("/resume/upload", files={"file": ("resume.pdf", f, "application/pdf")})
    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "resume.pdf"


def test_upload_resume_rejects_non_pdf(client):
    response = client.post("/resume/upload", files={"file": ("resume.txt", b"not a pdf", "text/plain")})
    assert response.status_code == 400


def test_upload_job_description_endpoint(client, sample_pdf):
    with open(sample_pdf, "rb") as f:
        response = client.post(
            "/jobs/upload",
            data={"company": "Acme", "role": "Backend Engineer"},
            files={"file": ("jd.pdf", f, "application/pdf")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["company"] == "Acme"
    assert body["role"] == "Backend Engineer"


def test_paste_job_description_endpoint(client):
    response = client.post(
        "/jobs/paste",
        json={"company": "Globex", "role": "Data Engineer", "raw_text": "Looking for a data engineer."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["company"] == "Globex"
