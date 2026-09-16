from typing import Any, TypedDict


class ToolCall(TypedDict):
    """One routing decision: which tool to run this turn, and with what arguments."""

    name: str
    args: dict[str, Any]


class AgentState(TypedDict):
    """State passed between LangGraph nodes for one agent turn."""

    messages: list[dict]
    current_task: str
    tool_results: list[dict]
    final_response: str
    error: str | None
    tool_call: ToolCall | None
