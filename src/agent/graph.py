from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent.nodes import (
    make_dispatch_executor,
    make_router_node,
    make_tool_node,
    memory_update_node,
    parse_intent_node,
    response_node,
)
from src.agent.state import AgentState


def _route_after_router(state: AgentState) -> str:
    """Conditional-edge function for the router's outgoing edge.

    LangGraph calls this with the current state after `router` runs, and
    looks whatever string it returns up in the mapping passed to
    add_conditional_edges below -- that lookup is the entire branching
    mechanism. Three outcomes: the router's own LLM call failed (surface the
    error via response_node, same formatting path a failed tool uses), the
    router picked a tool (run it), or the router just answered in plain text
    (skip straight to recording that reply -- there's nothing left to run).
    """
    if state["error"]:
        return "error"
    if state["tool_call"] is not None:
        return "tool"
    return "direct_reply"


def _route_after_tool(state: AgentState) -> str:
    """Loop for another model decision until the three-tool limit is reached."""
    if state["error"] or state["tool_call_count"] >= 3:
        return "response"
    return "router"


def build_graph(
    *,
    router_node: Any | None = None,
    tool_node: Any | None = None,
) -> CompiledStateGraph:
    """Assemble and compile the JAM agent graph.

    Wires every node in src/agent/nodes.py into the flow CLAUDE.md's
    architecture diagram describes:

        parse_intent -> router -> [tool -> response | response (error) | memory_update (direct reply)]
                                                            \\-> memory_update -> END

    `router_node`/`tool_node` are injectable so tests (or a manual smoke run)
    can supply fakes instead of a real Anthropic-backed router and a real
    database-backed tool dispatcher -- same dependency-injection pattern used
    throughout src/llm/*.py and src/agent/nodes.py itself.
    """
    graph = StateGraph(AgentState)

    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("router", router_node or make_router_node())
    graph.add_node("run_tool", tool_node or make_tool_node(make_dispatch_executor()))
    graph.add_node("response", response_node)
    graph.add_node("memory_update", memory_update_node)

    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "router")
    graph.add_conditional_edges(
        "router",
        _route_after_router,
        {"error": "response", "tool": "run_tool", "direct_reply": "memory_update"},
    )
    graph.add_conditional_edges(
        "run_tool",
        _route_after_tool,
        {"router": "router", "response": "response"},
    )
    graph.add_edge("response", "memory_update")
    graph.add_edge("memory_update", END)

    return graph.compile()
