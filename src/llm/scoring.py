import json
from typing import Callable

from src.llm.clients import generate_with_anthropic


def score_match(
    resume_text: str,
    job_text: str,
    *,
    generator: Callable[..., str] = generate_with_anthropic,
) -> dict:
    """Score how well a resume matches a job description, with a gap analysis.

    Returns {"match_score": float in [0.0, 1.0], "gap_analysis": str}. match_score
    is written to applications.match_score; gap_analysis is stored as a
    tailoring_suggestions row in generated_documents so the user can see why a
    score landed where it did.
    """
    prompt = (
        "Compare this resume against this job description. Respond with ONLY a "
        "JSON object in exactly this shape, no other text:\n"
        '{"match_score": <float 0.0-1.0>, "gap_analysis": "<4-5 sentences on '
        'missing or weak skills/experience relative to the job>"}\n\n'
        f"RESUME:\n{resume_text}\n\n"
        f"JOB DESCRIPTION:\n{job_text}"
    )
    raw = generator(
        prompt,
        system="You are a precise technical recruiter. Output only valid JSON.",
        max_tokens=500,
    ).strip()
    data = json.loads(_strip_code_fence(raw))
    return {
        "match_score": max(0.0, min(1.0, float(data["match_score"]))),
        "gap_analysis": str(data["gap_analysis"]).strip(),
    }


def _strip_code_fence(text: str) -> str:
    """Strip a ```json ... ``` fence if the model wrapped its JSON output in one."""
    if not text.startswith("```"):
        return text
    text = text.split("\n", 1)[1] if "\n" in text else ""
    if text.endswith("```"):
        text = text[:-3]
    elif "```" in text:
        text = text.rsplit("```", 1)[0]
    return text.strip()
