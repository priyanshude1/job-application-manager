from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.agent import tools
from src.database import crud
from src.database.connection import get_db

router = APIRouter(prefix="/emails", tags=["emails"])


def _serialize_email_event(event) -> dict:
    return {
        "id": event.id,
        "application_id": event.application_id,
        "subject": event.subject,
        "snippet": event.snippet,
        "detected_intent": event.detected_intent,
        "status_change": event.status_change,
        "received_at": event.received_at,
    }


@router.post("/sync")
def sync_emails(db: Session = Depends(get_db)) -> dict:
    """Trigger a Gmail sync: fetch recent emails for every known company,
    classify intent, and auto-update application statuses.

    Delegates straight to tools.parse_emails_tool -- the exact same function
    the chat agent calls for this -- rather than re-implementing the fetch/
    classify/update flow here. That keeps this logic in one place instead of
    the API and the agent silently drifting apart over time.
    """
    result = tools.parse_emails_tool(db)
    if not result["success"]:
        raise HTTPException(status_code=502, detail=result.get("error", "Gmail sync failed"))
    return result


@router.get("/{application_id}")
def list_email_events(application_id: int, db: Session = Depends(get_db)) -> dict:
    application = crud.get_application(db, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    events = crud.list_email_events_for_application(db, application_id)
    return {
        "application_id": application_id,
        "events": [_serialize_email_event(event) for event in events],
    }
