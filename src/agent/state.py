from typing import TypedDict


class AgentState(TypedDict):
    """State passed between LangGraph nodes for one agent turn."""

    messages: list[dict]
    current_task: str
    tool_results: list[dict]
    final_response: str
    error: str | None
