import os
from typing import Any


def get_anthropic_client() -> Any:
    """Create the Anthropic client when an LLM feature actually needs it."""
    from anthropic import Anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return Anthropic(api_key=api_key)


def get_anthropic_model() -> str:
    return os.getenv("HAIKU_MODEL", "claude-haiku-4-5")


def get_openrouter_client() -> Any:
    """Create the OpenRouter client when an email-classification feature needs it."""
    from openai import OpenAI

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    )


def get_openrouter_model() -> str:
    return os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free")