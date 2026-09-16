import os
from collections.abc import Callable
from typing import Any

from src.agent.state import AgentState

MEMORY_WINDOW_SIZE = int(os.getenv("MEMORY_WINDOW_SIZE", "8"))
TOOL_RESULT_MAX_TOKENS = int(os.getenv("TOOL_RESULT_MAX_TOKENS", "1000"))
ToolExecutor = Callable[[AgentState], dict[str, Any]]


def parse_intent_node(state: AgentState) -> dict[str, Any]:
    """Prepare the latest user message for routing.

    Intent classification belongs to the graph's model-backed router. This node
    only establishes a deterministic current-task value and clears stale output
    from the previous turn.
    """
    user_messages = [message for message in state["messages"] if message.get("role") == "user"]
    latest_message = user_messages[-1].get("content", "") if user_messages else ""
    return {
        "current_task": str(latest_message).strip(),
        "tool_results": [],
        "final_response": "",
        "error": None,
    }


def make_tool_node(executor: ToolExecutor) -> Callable[[AgentState], dict[str, Any]]:
    """Adapt an injected capability executor to a graph node."""
    def tool_node(state: AgentState) -> dict[str, Any]:
        try:
            result = executor(state)
        except Exception as exc:
            return {"error": str(exc)}
        return {"tool_results": [*state["tool_results"], _truncate_result(result)]}

    return tool_node


def response_node(state: AgentState) -> dict[str, Any]:
    """Create a deterministic response from tool results or a node error."""
    if state["error"]:
        return {"final_response": f"I couldn't complete that request: {state['error']}"}
    if not state["tool_results"]:
        return {"final_response": "I couldn't find an action to take for that request."}

    latest_result = state["tool_results"][-1]
    if latest_result.get("success") is False:
        return {"final_response": latest_result.get("error", "The requested action failed.")}
    return {"final_response": str(latest_result)}


def memory_update_node(state: AgentState) -> dict[str, Any]:
    """Record this turn's reply in history, then keep only the recent window.

    response_node always runs immediately before this node in the graph, so
    state["final_response"] is guaranteed to be populated here. Without this
    append, the agent's own replies would never re-enter `messages`, so the
    next turn's LLM call would have no idea what it said last time.
    """
    messages = [*state["messages"], {"role": "assistant", "content": state["final_response"]}]
    return {"messages": messages[-MEMORY_WINDOW_SIZE:]}


def _truncate_result(result: dict[str, Any]) -> dict[str, Any]:
    """Limit large tool observations before they re-enter agent context."""
    serialized = str(result)
    if len(serialized) <= TOOL_RESULT_MAX_TOKENS * 4:
        return result
    truncated = dict(result)
    truncated["_truncated"] = True
    truncated["_observation"] = serialized[: TOOL_RESULT_MAX_TOKENS * 4]
    return truncated
