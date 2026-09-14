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
    return os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")


def get_sonnet_model() -> str:
    return os.getenv("SONNET_MODEL", "claude-sonnet-5")


def generate_with_anthropic(
    prompt: str,
    *,
    system: str = "You are a precise assistant for a job application manager.",
    max_tokens: int = 2048,
    client: Any | None = None,
) -> str:
    """Send one prompt to the configured Anthropic model and return its text."""
    active_client = client or get_anthropic_client()
    response = active_client.messages.create(
        model=get_anthropic_model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


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


def generate_with_openrouter(
    prompt: str,
    *,
    system: str = "You classify and extract information accurately.",
    max_tokens: int = 512,
    client: Any | None = None,
) -> str:
    """Send one prompt to the configured OpenRouter model and return its text."""
    active_client = client or get_openrouter_client()
    response = active_client.chat.completions.create(
        model=get_openrouter_model(),
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content