from typing import Callable

from src.llm.clients import generate_with_anthropic
from src.llm.cv_tailoring import CompileResult, compile_latex

MAX_COVER_LETTER_RETRIES = 3

COVER_LETTER_SYSTEM_PROMPT = """You write cover letters that sound like thoughtful, capable people, not AI.

Write a warm, confident, direct cover letter of 300-400 words in 3-4 focused paragraphs. Make the letter specific to the candidate, company, and role. Use natural sentence variety, concrete details from the resume, and genuine motivation grounded in the job description, don't use the same keywords given in the job description. Be confident without exaggerating and personable without becoming casual or overly familiar.

Avoid generic or inflated language and common AI-sounding phrases such as "passionate about," "delighted to apply," "leverage my skills," "proven track record," "dynamic environment," "unique blend," "aligns perfectly," "I am confident that," "I would welcome the opportunity," and "I look forward to hearing from you." Do not use buzzword-heavy claims, empty compliments, repetitive conclusions, rhetorical filler, or made-up facts. Do not mention AI, prompts, language models, or this instruction.

Output only a complete, compilable standalone LaTeX document using the article class. Keep the letter body between 300 and 400 words and organize it into exactly 3 or 4 focused paragraphs. Do not output Markdown fences or any explanation."""


def generate_cover_letter(
    resume_text: str,
    job_text: str,
    company: str,
    role: str,
    *,
    generator: Callable[..., str] = generate_with_anthropic,
) -> str:
    """Generate standalone LaTeX for one cover letter."""
    prompt = (
        f"Write a concise, specific LaTeX cover letter for the {role} role at {company}. "
        "Return a complete, compilable standalone .tex document using the article "
        "class. Use only facts supported by the resume. Do not invent experience, "
        "metrics, or contact details. Return only LaTeX source with no markdown fences.\n\n"
        f"RESUME:\n{resume_text}\n\n"
        f"JOB DESCRIPTION:\n{job_text}"
    )
    latex = generator(
        prompt,
        system=COVER_LETTER_SYSTEM_PROMPT,
        max_tokens=2400,
    ).strip()
    return _strip_code_fence(latex)


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    text = text.split("\n", 1)[1] if "\n" in text else ""
    if text.endswith("```"):
        text = text[:-3]
    elif "```" in text:
        text = text.rsplit("```", 1)[0]
    return text.strip()


def generate_and_compile_cover_letter(
    resume_text: str,
    job_text: str,
    company: str,
    role: str,
    output_dir: str,
    basename: str,
    *,
    generator: Callable[..., str] = generate_with_anthropic,
    compiler: Callable[[str, str, str], CompileResult] = compile_latex,
    max_retries: int = MAX_COVER_LETTER_RETRIES,
) -> dict:
    """Generate and compile a cover letter, feeding compiler errors back to the LLM."""
    error_feedback: str | None = None
    latex_source = ""

    for attempt in range(max_retries + 1):
        prompt_generator = generator
        if error_feedback:
            prompt_generator = _generator_with_feedback(generator, error_feedback)
        latex_source = generate_cover_letter(
            resume_text,
            job_text,
            company,
            role,
            generator=prompt_generator,
        )
        result = compiler(latex_source, output_dir, basename)
        if result.success:
            return {
                "success": True,
                "latex_source": latex_source,
                "pdf_path": result.pdf_path,
                "attempts": attempt + 1,
                "error": None,
            }
        error_feedback = result.error

    return {
        "success": False,
        "latex_source": latex_source,
        "pdf_path": None,
        "attempts": max_retries + 1,
        "error": error_feedback,
    }


def _generator_with_feedback(
    generator: Callable[..., str], error_feedback: str
) -> Callable[..., str]:
    def generate_with_feedback(prompt: str, **kwargs: object) -> str:
        return generator(
            f"{prompt}\n\nThe previous LaTeX failed to compile. Fix this tectonic error "
            f"while preserving the letter:\n{error_feedback}",
            **kwargs,
        )

    return generate_with_feedback