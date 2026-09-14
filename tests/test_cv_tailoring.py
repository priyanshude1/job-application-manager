import subprocess

from src.llm.cv_tailoring import (
    CompileResult,
    compile_latex,
    generate_tailored_latex,
    tailor_and_compile_cv,
)


def test_generate_tailored_latex_includes_resume_job_and_template_in_prompt():
    captured: dict[str, object] = {}

    def fake_generator(prompt: str, **kwargs: object) -> str:
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return r"\documentclass{article}\begin{document}Tailored CV\end{document}"

    result = generate_tailored_latex(
        "Python engineer with SQL experience.",
        "Looking for a backend engineer with Python.",
        r"\documentclass{article}\begin{document}Template\end{document}",
        generator=fake_generator,
    )

    assert result == r"\documentclass{article}\begin{document}Tailored CV\end{document}"
    assert "Python engineer with SQL experience." in captured["prompt"]
    assert "Looking for a backend engineer with Python." in captured["prompt"]
    assert r"\documentclass{article}\begin{document}Template\end{document}" in captured["prompt"]
    assert captured["kwargs"] == {
        "system": "You are a meticulous LaTeX editor. Output only valid .tex source.",
        "max_tokens": 4000,
    }


def test_generate_tailored_latex_strips_markdown_fence():
    def fake_generator(prompt: str, **kwargs: object) -> str:
        return "```latex\n\\documentclass{article}\n```"

    result = generate_tailored_latex("resume", "job", "template", generator=fake_generator)

    assert result == r"\documentclass{article}"


def test_generate_tailored_latex_includes_error_feedback_when_retrying():
    captured: dict[str, object] = {}

    def fake_generator(prompt: str, **kwargs: object) -> str:
        captured["prompt"] = prompt
        return r"\documentclass{article}"

    generate_tailored_latex(
        "resume",
        "job",
        "template",
        generator=fake_generator,
        error_feedback=r"Undefined control sequence \foo on line 12.",
    )

    assert r"Undefined control sequence \foo on line 12." in captured["prompt"]


def test_compile_latex_writes_tex_file_and_compiles_successfully(tmp_path):
    def fake_runner(tex_path, output_dir):
        assert tex_path.read_text(encoding="utf-8") == r"\documentclass{article}"
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    result = compile_latex(
        r"\documentclass{article}",
        str(tmp_path),
        "cv_acme",
        runner=fake_runner,
    )

    assert result == CompileResult(
        success=True, pdf_path=str(tmp_path / "cv_acme.pdf"), error=None
    )
    assert (tmp_path / "cv_acme.tex").exists()


def test_compile_latex_returns_compiler_error_on_failure(tmp_path):
    def fake_runner(tex_path, output_dir):
        return subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="! Undefined control sequence."
        )

    result = compile_latex(
        r"\documentclass{article}", str(tmp_path), "cv_acme", runner=fake_runner
    )

    assert result == CompileResult(
        success=False, pdf_path=None, error="! Undefined control sequence."
    )


def test_tailor_and_compile_cv_succeeds_on_first_attempt(tmp_path):
    def fake_generator(prompt: str, **kwargs: object) -> str:
        return r"\documentclass{article}"

    def fake_compiler(latex_source: str, output_dir: str, basename: str) -> CompileResult:
        return CompileResult(success=True, pdf_path=f"{output_dir}/{basename}.pdf", error=None)

    result = tailor_and_compile_cv(
        "resume",
        "job",
        "template",
        str(tmp_path),
        "cv_acme",
        generator=fake_generator,
        compiler=fake_compiler,
    )

    assert result["success"] is True
    assert result["attempts"] == 1
    assert result["error"] is None
    assert result["pdf_path"] == f"{tmp_path}/cv_acme.pdf"


def test_tailor_and_compile_cv_retries_with_compiler_error_fed_back(tmp_path):
    prompts_seen: list[str] = []
    attempts = {"n": 0}

    def fake_generator(prompt: str, **kwargs: object) -> str:
        prompts_seen.append(prompt)
        return r"\documentclass{article}"

    def fake_compiler(latex_source: str, output_dir: str, basename: str) -> CompileResult:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return CompileResult(
                success=False, pdf_path=None, error=r"! Undefined control sequence \foo."
            )
        return CompileResult(success=True, pdf_path=f"{output_dir}/{basename}.pdf", error=None)

    result = tailor_and_compile_cv(
        "resume",
        "job",
        "template",
        str(tmp_path),
        "cv_acme",
        generator=fake_generator,
        compiler=fake_compiler,
    )

    assert result["success"] is True
    assert result["attempts"] == 2
    assert len(prompts_seen) == 2
    assert r"! Undefined control sequence \foo." not in prompts_seen[0]
    assert r"! Undefined control sequence \foo." in prompts_seen[1]


def test_tailor_and_compile_cv_reports_failure_after_exhausting_retries(tmp_path):
    def fake_generator(prompt: str, **kwargs: object) -> str:
        return r"\documentclass{article}"

    def fake_compiler(latex_source: str, output_dir: str, basename: str) -> CompileResult:
        return CompileResult(success=False, pdf_path=None, error="! Missing $ inserted.")

    result = tailor_and_compile_cv(
        "resume",
        "job",
        "template",
        str(tmp_path),
        "cv_acme",
        generator=fake_generator,
        compiler=fake_compiler,
        max_retries=1,
    )

    assert result["success"] is False
    assert result["attempts"] == 2
    assert result["pdf_path"] is None
    assert result["error"] == "! Missing $ inserted."
