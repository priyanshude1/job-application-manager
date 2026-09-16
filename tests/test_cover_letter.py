from src.llm.cover_letter import (
    COVER_LETTER_SYSTEM_PROMPT,
    generate_and_compile_cover_letter,
    generate_cover_letter,
)
from src.llm.cv_tailoring import CompileResult


def test_generate_cover_letter_uses_resume_and_job_context():
    captured: dict[str, object] = {}

    def fake_generator(prompt: str, **kwargs: object) -> str:
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return "```latex\n\\documentclass{article}\n\\begin{document}Letter\\end{document}\n```"

    result = generate_cover_letter(
        "Python engineer with SQL experience.",
        "Looking for a backend engineer with Python.",
        "Acme",
        "Backend Engineer",
        generator=fake_generator,
    )

    assert result == "\\documentclass{article}\n\\begin{document}Letter\\end{document}"
    assert "Python engineer with SQL experience." in captured["prompt"]
    assert "Looking for a backend engineer with Python." in captured["prompt"]
    assert "Backend Engineer" in captured["prompt"]
    assert "300-400 words" in captured["kwargs"]["system"]
    assert "3 or 4 focused paragraphs" in captured["kwargs"]["system"]
    assert "passionate about" in captured["kwargs"]["system"]
    assert captured["kwargs"]["system"] == COVER_LETTER_SYSTEM_PROMPT
    assert captured["kwargs"] == {
        "system": COVER_LETTER_SYSTEM_PROMPT,
        "max_tokens": 2400,
    }


def test_generate_and_compile_cover_letter_retries_with_error_feedback(tmp_path):
    prompts_seen: list[str] = []
    attempts = {"count": 0}

    def fake_generator(prompt: str, **kwargs: object) -> str:
        prompts_seen.append(prompt)
        return r"\documentclass{article}\begin{document}Letter\end{document}"

    def fake_compiler(latex_source: str, output_dir: str, basename: str) -> CompileResult:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return CompileResult(False, None, "missing brace")
        return CompileResult(True, f"{output_dir}/{basename}.pdf", None)

    result = generate_and_compile_cover_letter(
        "resume",
        "job",
        "Acme",
        "Backend Engineer",
        str(tmp_path),
        "cover_letter_acme",
        generator=fake_generator,
        compiler=fake_compiler,
    )

    assert result["success"] is True
    assert result["attempts"] == 2
    assert "missing brace" in prompts_seen[1]