import fitz


def parse_job_description(raw_text: str | None = None, file_path: str | None = None) -> str:
    """Produce the stored job description text from either input method.

    Job descriptions arrive as either pasted text or an uploaded PDF, never
    both. Regardless of which one is used, this returns the same shape of
    output — the value written to `job_descriptions.raw_text` — so every
    downstream LLM pipeline reads `raw_text` without caring how the job
    description was originally submitted.
    """
    if raw_text is not None:
        return raw_text.strip()

    if file_path is not None:
        with fitz.open(file_path) as doc:
            pages = [page.get_text() for page in doc]
        return "\n\n".join(pages).strip()

    raise ValueError("Either raw_text or file_path must be provided")
