from src.llm.clients import generate_with_openrouter

DETECTED_INTENTS = [
    "interview_invite",
    "rejection",
    "offer",
    "follow_up",
    "submission_confirmation",
    "unknown",
]

# Only these intents imply an automatic status change -- interview_invite/rejection/offer
# are unambiguous funnel transitions. follow_up and submission_confirmation are handled
# without touching status (submission_confirmation instead sets confirmed_at/
# confirmation_source, per CLAUDE.md); unknown covers emails that matched the Gmail
# search but aren't actually about this application at all (newsletters, unrelated
# mentions) -- there is no status for "we don't know what this was."
INTENT_STATUS_MAP = {
    "interview_invite": "Interview Scheduled",
    "rejection": "Rejected",
    "offer": "Offer",
}

EMAIL_INTENT_SYSTEM_PROMPT = (
    "You classify job-application emails by intent. Read the subject and body "
    "snippet, then reply with exactly one word from this list and nothing else: "
    f"{', '.join(DETECTED_INTENTS)}.\n\n"
    "interview_invite: inviting the candidate to an interview or next round.\n"
    "rejection: declining the application.\n"
    "offer: extending a job offer.\n"
    "follow_up: a recruiter/company follow-up that is not a rejection, offer, or "
    "interview invite (e.g. requesting more information, a check-in).\n"
    "submission_confirmation: confirming a submitted application was received.\n"
    "unknown: anything else, including emails unrelated to a real job application "
    "(newsletters, marketing, or the company name appearing for an unrelated reason)."
)


def classify_email_intent(subject: str, snippet: str, *, client=None) -> str:
    """Classify one email's job-application intent using the free OpenRouter model.

    Calls generate_with_openrouter (src/llm/clients.py) rather than an SDK
    directly -- every LLM call in this project is centralized there. Always
    returns a value from DETECTED_INTENTS, defaulting to "unknown" both when
    the call itself fails (network error, misconfigured key) and when the
    model's reply doesn't cleanly match one of the expected words -- a free,
    small model occasionally adds punctuation or extra words, and "unknown"
    is the same safe fallback already used for genuinely unrelated emails.
    """
    prompt = f"Subject: {subject}\n\nBody snippet: {snippet}"
    try:
        reply = generate_with_openrouter(prompt, system=EMAIL_INTENT_SYSTEM_PROMPT, max_tokens=20, client=client)
    except Exception:
        return "unknown"

    normalized = reply.strip().lower().strip(".")
    return normalized if normalized in DETECTED_INTENTS else "unknown"
