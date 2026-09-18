from collections.abc import Callable
from typing import Any, TypeVar

Function = TypeVar("Function", bound=Callable[..., Any])


def trace_llm_call(name: str) -> Callable[[Function], Function]:
    """Trace an LLM client call when LangSmith is installed and configured.

    LangSmith reads LANGCHAIN_TRACING_V2, LANGCHAIN_API_KEY, and
    LANGCHAIN_PROJECT from the environment. Keeping the import lazy makes
    local unit tests and non-tracing development work without the package.
    """
    def decorator(function: Function) -> Function:
        try:
            from langsmith import traceable
        except ImportError:
            return function
        return traceable(name=name, run_type="llm")(function)

    return decorator
