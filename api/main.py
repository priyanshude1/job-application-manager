from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from src.database.connection import SessionLocal, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Job Application Manager", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    db_status = "ok"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_status = "error"

    return {
        "status": "ok",
        "db": db_status,
        "mlflow": "not_configured",
        "gmail_mcp": "not_configured",
    }
