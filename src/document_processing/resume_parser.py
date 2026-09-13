import fitz


def parse_resume_pdf(file_path: str) -> str:
    """Extract plain text from a resume PDF.

    Reads every page of the PDF at `file_path` and concatenates their text,
    in order, separated by blank lines. This is the only way resume text
    enters the system — the result is what gets stored in
    `resumes.parsed_text` and what every later LLM pipeline (scoring, cover
    letter generation) reads instead of re-parsing the PDF each time.
    """
    with fitz.open(file_path) as doc:
        pages = [page.get_text() for page in doc]
    return "\n\n".join(pages).strip()
