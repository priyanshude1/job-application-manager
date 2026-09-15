import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jam.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if "applications" not in inspect(engine).get_table_names():
        return

    application_columns = {
        column["name"] for column in inspect(engine).get_columns("applications")
    }
    if "submission_method" not in application_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE applications ADD COLUMN "
                    "submission_method VARCHAR NOT NULL DEFAULT 'manual'"
                )
            )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
