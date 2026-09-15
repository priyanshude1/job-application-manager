import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import Base, GeneratedDocument

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jam.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _migrate_applications_table() -> None:
    """Bring an existing applications table up to the current schema.

    All three changes are safe as plain ADD COLUMN / RENAME COLUMN statements
    (SQLite 3.25+ supports both directly) -- no table rebuild needed. Note:
    submitted_at's NOT NULL is enforced at the app layer (create_application
    always supplies utcnow() when omitted), not as a hard SQLite constraint on
    an already-migrated table -- SQLite can't retroactively add NOT NULL
    without a full rebuild, and rebuilding applications specifically isn't
    worth the real-data risk for a guarantee the app layer already provides.
    """
    columns = {column["name"] for column in inspect(engine).get_columns("applications")}
    with engine.begin() as connection:
        if "submission_method" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE applications ADD COLUMN "
                    "submission_method VARCHAR NOT NULL DEFAULT 'manual'"
                )
            )
        if "date_applied" in columns and "submitted_at" not in columns:
            connection.execute(
                text("ALTER TABLE applications RENAME COLUMN date_applied TO submitted_at")
            )
        if "confirmed_at" not in columns:
            connection.execute(text("ALTER TABLE applications ADD COLUMN confirmed_at DATETIME"))
        if "confirmation_source" not in columns:
            connection.execute(
                text("ALTER TABLE applications ADD COLUMN confirmation_source VARCHAR")
            )


def _migrate_generated_documents_table() -> None:
    """Relax generated_documents.application_id to nullable, add resume_id/job_id.

    SQLite has no ALTER COLUMN, so relaxing a NOT NULL constraint (and adding
    two new required FK columns) needs a table rebuild rather than ADD COLUMN.
    No /generate/* endpoint exists yet to have written real rows here in any
    actual deployment, so this checks for real data rather than assuming --
    empty tables are simply dropped and recreated; if rows are found, they're
    rebuilt without loss, since every pre-migration row has a non-null
    application_id and resume_id/job_id are always recoverable via a join to
    applications.
    """
    columns = {column["name"] for column in inspect(engine).get_columns("generated_documents")}
    if "resume_id" in columns and "job_id" in columns:
        return  # already the current shape

    with engine.begin() as connection:
        row_count = connection.execute(text("SELECT COUNT(*) FROM generated_documents")).scalar()

        if row_count == 0:
            connection.execute(text("DROP TABLE generated_documents"))
            GeneratedDocument.__table__.create(bind=connection)
        else:
            connection.execute(
                text("ALTER TABLE generated_documents RENAME TO generated_documents_old")
            )
            GeneratedDocument.__table__.create(bind=connection)
            connection.execute(
                text(
                    """
                    INSERT INTO generated_documents
                        (id, application_id, resume_id, job_id, doc_type, content_text,
                         file_path, prompt_version, match_score, created_at)
                    SELECT god.id, god.application_id, a.resume_id, a.job_id,
                           CASE WHEN god.doc_type = 'tailoring_suggestions' THEN 'score'
                                ELSE god.doc_type END,
                           god.content_text, god.file_path, god.prompt_version,
                           CASE WHEN god.doc_type = 'tailoring_suggestions' THEN a.match_score
                                ELSE NULL END,
                           god.created_at
                    FROM generated_documents_old god
                    JOIN applications a ON a.id = god.application_id
                    """
                )
            )
            connection.execute(text("DROP TABLE generated_documents_old"))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    table_names = inspect(engine).get_table_names()
    if "applications" in table_names:
        _migrate_applications_table()
    if "generated_documents" in table_names:
        _migrate_generated_documents_table()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
