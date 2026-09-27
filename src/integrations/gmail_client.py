import os
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service(
    *,
    credentials_path: str | None = None,
    token_path: str | None = None,
) -> Any:
    """Build an authenticated Gmail API service client.

    Single-user, local, one-time OAuth: the first call opens a browser for
    consent (google_auth_oauthlib's InstalledAppFlow) and caches the
    resulting refresh token at `token_path`; every call after that silently
    reuses/refreshes it -- no repeated consent, no web redirect flow (that
    machinery is for multi-user web apps, which this isn't). Imports the
    google-* libraries lazily, same pattern as get_anthropic_client and
    get_openrouter_client in src/llm/clients.py, so importing this module
    doesn't require them installed unless Gmail sync is actually used.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    credentials_file = Path(
        credentials_path or os.getenv("GMAIL_CREDENTIALS_PATH", "./data/gmail_credentials.json")
    )
    token_file = Path(token_path or os.getenv("GMAIL_TOKEN_PATH", "./data/gmail_token.json"))

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_file.exists():
                raise RuntimeError(
                    f"Gmail OAuth client secret not found at {credentials_file}. "
                    "Create one in Google Cloud Console (OAuth client, type "
                    "'Desktop app'), download it there, or point "
                    "GMAIL_CREDENTIALS_PATH at it."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def fetch_recent_emails(
    service: Any,
    *,
    company_names: list[str],
    days: int = 7,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """Fetch recent Gmail messages from any of the given companies.

    Builds one Gmail search query -- `newer_than:{days}d` narrowed to an OR
    of `from:`/`subject:` per company -- so filtering happens server-side
    instead of pulling the whole inbox into Python. Returns one plain dict
    per message with just what email_events/intent classification need, so
    callers never touch the raw Gmail API response shape (nested payload,
    header list, etc).
    """
    if not company_names:
        return []

    per_company = " OR ".join(f'(from:"{name}" OR subject:"{name}")' for name in company_names)
    query = f"newer_than:{days}d ({per_company})"

    response = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    message_refs = response.get("messages", [])

    emails = []
    for ref in message_refs:
        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=ref["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            )
            .execute()
        )
        headers = {header["name"]: header["value"] for header in message["payload"]["headers"]}
        emails.append(
            {
                "raw_email_id": message["id"],
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "received_at": _parse_date_header(headers.get("Date")),
                "snippet": message.get("snippet", "")[:200],
            }
        )
    return emails


def _parse_date_header(date_header: str | None):
    """Parse an RFC 2822 email Date header into a datetime, or None if absent/malformed."""
    if not date_header:
        return None
    try:
        return parsedate_to_datetime(date_header)
    except (TypeError, ValueError):
        return None
