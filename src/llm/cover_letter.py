from typing import Callable

from src.llm.clients import generate_with_anthropic


def generate_cover_letter(
    resume_text: str,
    job_text: str,
    company: str,
    role: str,
    *,
    generator: Callable[..., str] = generate_with_anthropic,
) -> str:
    """Generate one cover letter from a resume and job description."""
    prompt = (
        f"Write a concise, specific cover letter for the {role} role at {company}. "
        "Use only facts supported by the resume. Do not invent experience, metrics, "
        "or contact details. Return only the letter.\n\n"
        f"RESUME:\n{resume_text}\n\n"
        f"JOB DESCRIPTION:\n{job_text}"
    )
    return generator(
        prompt,
        system="Write professional, truthful cover letters.",
        max_tokens=1600,
    ).strip()