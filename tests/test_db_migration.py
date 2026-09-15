from sqlalchemy import create_engine, text

import src.database.connection as connection


def _seed_legacy_db(db_path, *, with_generated_documents_rows: bool):
    """Build a SQLite file shaped like the schema before this migration existed."""
    seed_engine = create_engine(f"sqlite:///{db_path}")
    with seed_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE applications (
                id INTEGER PRIMARY KEY, resume_id INTEGER, job_id INTEGER,
                date_applied DATETIME, status VARCHAR, match_score FLOAT,
                notes TEXT, created_at DATETIME, updated_at DATETIME
            )
        """))
        conn.execute(text(
            "INSERT INTO applications (id, resume_id, job_id, status, match_score) "
            "VALUES (1, 42, 99, 'Applied', 0.77)"
        ))
        conn.execute(text("""
            CREATE TABLE generated_documents (
                id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL,
                doc_type VARCHAR, content_text TEXT, file_path VARCHAR,
                prompt_version VARCHAR, created_at DATETIME
            )
        """))
        if with_generated_documents_rows:
            conn.execute(text(
                "INSERT INTO generated_documents "
                "(id, application_id, doc_type, content_text, created_at) "
                "VALUES (1, 1, 'tailoring_suggestions', 'Missing Kubernetes experience.', "
                "'2026-09-01 10:00:00')"
            ))
            conn.execute(text(
                "INSERT INTO generated_documents "
                "(id, application_id, doc_type, content_text, created_at) "
                "VALUES (2, 1, 'cover_letter', 'Dear hiring team...', '2026-09-01 10:05:00')"
            ))
    seed_engine.dispose()


def _columns(engine, table_name):
    return {column["name"] for column in connection.inspect(engine).get_columns(table_name)}


def test_init_db_creates_fresh_schema_directly(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "engine", create_engine(f"sqlite:///{tmp_path / 'fresh.db'}"))
    connection.init_db()

    app_columns = _columns(connection.engine, "applications")
    doc_columns = _columns(connection.engine, "generated_documents")
    assert {"submitted_at", "confirmed_at", "confirmation_source", "submission_method"} <= app_columns
    assert "date_applied" not in app_columns
    assert {"resume_id", "job_id", "match_score"} <= doc_columns


def test_init_db_migrates_legacy_applications_columns(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    _seed_legacy_db(db_path, with_generated_documents_rows=False)
    monkeypatch.setattr(connection, "engine", create_engine(f"sqlite:///{db_path}"))

    connection.init_db()

    app_columns = _columns(connection.engine, "applications")
    assert "date_applied" not in app_columns
    assert {"submitted_at", "confirmed_at", "confirmation_source", "submission_method"} <= app_columns
    with connection.engine.begin() as conn:
        row = conn.execute(text(
            "SELECT submission_method FROM applications WHERE id = 1"
        )).fetchone()
    assert row.submission_method == "manual"


def test_init_db_drops_and_recreates_empty_generated_documents(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy_empty_docs.db"
    _seed_legacy_db(db_path, with_generated_documents_rows=False)
    monkeypatch.setattr(connection, "engine", create_engine(f"sqlite:///{db_path}"))

    connection.init_db()

    doc_columns = _columns(connection.engine, "generated_documents")
    assert {"resume_id", "job_id", "match_score"} <= doc_columns
    with connection.engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM generated_documents")).scalar()
    assert count == 0


def test_init_db_rebuilds_nonempty_generated_documents_with_backfill(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy_full_docs.db"
    _seed_legacy_db(db_path, with_generated_documents_rows=True)
    monkeypatch.setattr(connection, "engine", create_engine(f"sqlite:///{db_path}"))

    connection.init_db()

    with connection.engine.begin() as conn:
        score_row = conn.execute(text(
            "SELECT resume_id, job_id, doc_type, match_score, content_text "
            "FROM generated_documents WHERE id = 1"
        )).fetchone()
        letter_row = conn.execute(text(
            "SELECT resume_id, job_id, doc_type, match_score FROM generated_documents WHERE id = 2"
        )).fetchone()
        old_table = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'generated_documents_old'"
        )).fetchone()

    # resume_id/job_id recovered via the join back through applications
    assert (score_row.resume_id, score_row.job_id) == (42, 99)
    assert (letter_row.resume_id, letter_row.job_id) == (42, 99)
    # retired doc_type renamed, and its match_score backfilled from the parent application
    assert score_row.doc_type == "score"
    assert score_row.match_score == 0.77
    assert score_row.content_text == "Missing Kubernetes experience."
    # a doc_type that was never 'tailoring_suggestions' is left alone, with no invented score
    assert letter_row.doc_type == "cover_letter"
    assert letter_row.match_score is None
    # scratch rename table cleaned up
    assert old_table is None


def test_init_db_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy_idempotent.db"
    _seed_legacy_db(db_path, with_generated_documents_rows=True)
    monkeypatch.setattr(connection, "engine", create_engine(f"sqlite:///{db_path}"))

    connection.init_db()
    connection.init_db()  # should be a no-op, not raise or duplicate/lose data

    with connection.engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM generated_documents")).scalar()
    assert count == 2
