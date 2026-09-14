import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.llm.clients import generate_with_anthropic

MAX_LATEX_RETRIES = 3


@dataclass
class CompileResult:
    success: bool
    pdf_path: str | None
    error: str | None


def generate_tailored_latex(
    resume_text: str,
    job_text: str,
    template_text: str,
    *,
    generator: Callable[..., str] = generate_with_anthropic,
    error_feedback: str | None = None,
) -> str:
    """Ask the LLM to tailor a LaTeX CV template to a job description.

    On a retry after a failed compile, `error_feedback` carries the tectonic
    error so the LLM fixes the specific LaTeX mistake instead of regenerating
    blind.
    """
    instructions = (
        "Tailor the LaTeX CV template below to the job description, using only "
        "facts from the resume text. Keep the template's structure, packages, "
        "and commands intact -- only change content (bullet points, summary, "
        "skills, ordering) to emphasize relevant experience. Return ONLY the "
        "complete, compilable .tex source -- no explanation, no markdown fences."
    )
    if error_feedback:
        instructions += (
            "\n\nThe previous version of this LaTeX failed to compile with this "
            f"tectonic error -- fix it while preserving the tailoring:\n{error_feedback}"
        )
    prompt = (
        f"{instructions}\n\n"
        f"RESUME:\n{resume_text}\n\n"
        f"JOB DESCRIPTION:\n{job_text}\n\n"
        f"LATEX TEMPLATE:\n{template_text}"
    )
    latex = generator(
        prompt,
        system="You are a meticulous LaTeX editor. Output only valid .tex source.",
        max_tokens=4000,
    ).strip()
    return _strip_code_fence(latex)


def _strip_code_fence(text: str) -> str:
    """Strip a ``` ... ``` fence if the model wrapped its LaTeX output in one."""
    if not text.startswith("```"):
        return text
    text = text.split("\n", 1)[1] if "\n" in text else ""
    if text.endswith("```"):
        text = text[:-3]
    elif "```" in text:
        text = text.rsplit("```", 1)[0]
    return text.strip()


def compile_latex(
    tex_source: str,
    output_dir: str,
    basename: str,
    *,
    runner: Callable[[Path, Path], subprocess.CompletedProcess] | None = None,
) -> CompileResult:
    """Write LaTeX source to disk and compile it to PDF with tectonic.

    `runner` is injectable so callers (and tests) can stand in for the actual
    tectonic subprocess call.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    tex_path = output_path / f"{basename}.tex"
    tex_path.write_text(tex_source, encoding="utf-8")

    run = runner or _run_tectonic
    result = run(tex_path, output_path)
    if result.returncode == 0:
        return CompileResult(
            success=True, pdf_path=str(output_path / f"{basename}.pdf"), error=None
        )
    return CompileResult(success=False, pdf_path=None, error=result.stderr)


def _run_tectonic(tex_path: Path, output_dir: Path) -> subprocess.CompletedProcess:
    """Invoke the tectonic CLI, compiling one .tex file to PDF."""
    return subprocess.run(
        ["tectonic", "--outdir", str(output_dir), str(tex_path)],
        capture_output=True,
        text=True,
    )


def tailor_and_compile_cv(
    resume_text: str,
    job_text: str,
    template_text: str,
    output_dir: str,
    basename: str,
    *,
    generator: Callable[..., str] = generate_with_anthropic,
    compiler: Callable[[str, str, str], CompileResult] = compile_latex,
    max_retries: int = MAX_LATEX_RETRIES,
) -> dict:
    """Tailor a LaTeX CV to a job and compile it, retrying on compiler errors.

    Implements the retry loop from CLAUDE.md's LaTeX CV Strategy: LLM-generated
    LaTeX occasionally has syntax errors, so the tectonic error is fed back to
    the LLM (up to max_retries times) instead of failing the whole generation
    on the first bad compile.
    """
    error_feedback: str | None = None
    latex_source = ""
    for attempt in range(max_retries + 1):
        latex_source = generate_tailored_latex(
            resume_text,
            job_text,
            template_text,
            generator=generator,
            error_feedback=error_feedback,
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
