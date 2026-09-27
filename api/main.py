import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from api.routers import applications, chat, documents, emails, generate
from src.database.connection import SessionLocal, init_db

OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", "./outputs"))
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Job Application Manager", lifespan=lifespan)
app.include_router(documents.router)
app.include_router(applications.router)
app.include_router(generate.router)
app.include_router(chat.router)
app.include_router(emails.router)

# Compiled PDFs live under outputs/generated -- mounting the outputs/ parent
# (not generated/ itself) means a document's stored file_path
# ("outputs/generated/xxx.pdf") maps directly onto its download URL with no
# path rewriting needed on either side.
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")


def _gmail_status() -> str:
    """Report Gmail auth state without making a live API call -- a health
    check should be fast and local, so this only checks whether the OAuth
    client secret and cached token files exist on disk.
    """
    if Path(os.getenv("GMAIL_TOKEN_PATH", "./data/gmail_token.json")).exists():
        return "ok"
    if Path(os.getenv("GMAIL_CREDENTIALS_PATH", "./data/gmail_credentials.json")).exists():
        return "not_authenticated"
    return "not_configured"


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
        "gmail": _gmail_status(),
    }


# Registered last so it only catches what no API route above already matched --
# serves the dashboard at "/" and falls back to index.html for any unknown path
# (a bookmarked deep link, a page refresh) rather than a plain 404.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
