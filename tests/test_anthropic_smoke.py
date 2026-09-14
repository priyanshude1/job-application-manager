import os

import pytest
from dotenv import load_dotenv

from src.llm.clients import generate_with_anthropic


@pytest.mark.skipif(
    os.getenv("RUN_LLM_SMOKE_TEST") != "1",
    reason="Set RUN_LLM_SMOKE_TEST=1 to make the paid Haiku smoke test run",
)
def test_anthropic_haiku_smoke(monkeypatch):
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY is not configured")

    monkeypatch.setenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")
    response = generate_with_anthropic(
        "Reply with exactly: OK",
        system="Return only OK.",
        max_tokens=8,
    )

    assert response.strip() == "OK"