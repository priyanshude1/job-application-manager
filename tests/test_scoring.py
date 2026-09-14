import json

from src.llm.scoring import score_match


def test_score_match_parses_json_response():
    captured: dict[str, object] = {}

    def fake_generator(prompt: str, **kwargs: object) -> str:
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return json.dumps({"match_score": 0.82, "gap_analysis": "Missing Kubernetes experience."})

    result = score_match(
        "Python engineer with SQL experience.",
        "Looking for a backend engineer with Python and Kubernetes.",
        generator=fake_generator,
    )

    assert result == {"match_score": 0.82, "gap_analysis": "Missing Kubernetes experience."}
    assert "Python engineer with SQL experience." in captured["prompt"]
    assert "Looking for a backend engineer with Python and Kubernetes." in captured["prompt"]
    assert captured["kwargs"] == {
        "system": "You are a precise technical recruiter. Output only valid JSON.",
        "max_tokens": 500,
    }


def test_score_match_strips_markdown_code_fence():
    def fake_generator(prompt: str, **kwargs: object) -> str:
        return '```json\n{"match_score": 0.5, "gap_analysis": "Some gaps."}\n```'

    result = score_match("resume", "job", generator=fake_generator)

    assert result == {"match_score": 0.5, "gap_analysis": "Some gaps."}


def test_score_match_clamps_out_of_range_scores():
    def fake_generator(prompt: str, **kwargs: object) -> str:
        return json.dumps({"match_score": 1.4, "gap_analysis": "Overqualified."})

    result = score_match("resume", "job", generator=fake_generator)

    assert result["match_score"] == 1.0
