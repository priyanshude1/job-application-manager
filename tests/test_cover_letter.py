from src.llm.cover_letter import generate_cover_letter


def test_generate_cover_letter_uses_resume_and_job_context():
    captured: dict[str, object] = {}

    def fake_generator(prompt: str, **kwargs: object) -> str:
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return "  Dear Acme hiring team,\n\nI am a strong fit.  "

    result = generate_cover_letter(
        "Python engineer with SQL experience.",
        "Looking for a backend engineer with Python.",
        "Acme",
        "Backend Engineer",
        generator=fake_generator,
    )

    assert result == "Dear Acme hiring team,\n\nI am a strong fit."
    assert "Python engineer with SQL experience." in captured["prompt"]
    assert "Looking for a backend engineer with Python." in captured["prompt"]
    assert "Backend Engineer" in captured["prompt"]
    assert captured["kwargs"] == {
        "system": "Write professional, truthful cover letters.",
        "max_tokens": 1600,
    }