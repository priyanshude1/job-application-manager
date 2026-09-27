import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.database.connection as connection
from api.main import app


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


def test_health_reports_gmail_not_configured_when_no_files_exist(client, monkeypatch, tmp_path):
    # Point both paths at files that don't exist in an isolated tmp_path, so this
    # test's result doesn't depend on whether Gmail has actually been set up in
    # the real repo (it has been, as of this session -- same class of ambient-
    # config isolation issue as the SQLite path fix elsewhere in this suite).
    monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", str(tmp_path / "missing_credentials.json"))
    monkeypatch.setenv("GMAIL_TOKEN_PATH", str(tmp_path / "missing_token.json"))

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["db"] == "ok"
    assert body["gmail"] == "not_configured"


def test_health_reports_gmail_not_authenticated_when_only_credentials_exist(client, monkeypatch, tmp_path):
    credentials_path = tmp_path / "gmail_credentials.json"
    credentials_path.write_text("{}")
    token_path = tmp_path / "gmail_token.json"

    monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", str(credentials_path))
    monkeypatch.setenv("GMAIL_TOKEN_PATH", str(token_path))

    response = client.get("/health")

    assert response.json()["gmail"] == "not_authenticated"


def test_health_reports_gmail_ok_when_token_cached(client, monkeypatch, tmp_path):
    token_path = tmp_path / "gmail_token.json"
    token_path.write_text("{}")

    monkeypatch.setenv("GMAIL_TOKEN_PATH", str(token_path))

    response = client.get("/health")

    assert response.json()["gmail"] == "ok"
