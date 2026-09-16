import os
from collections.abc import Callable
from typing import Any

import src.database.connection as connection
from src.agent import tools
from src.agent.state import AgentState
from src.llm.clients import generate_with_anthropic_tools

MEMORY_WINDOW_SIZE = int(os.getenv("MEMORY_WINDOW_SIZE", "8"))
TOOL_RESULT_MAX_TOKENS = int(os.getenv("TOOL_RESULT_MAX_TOKENS", "1000"))
ToolExecutor = Callable[[AgentState], dict[str, Any]]

_STATUS_ENUM = [
    "Applied",
    "Interview Scheduled",
    "Interview Done",
    "Offer",
    "Rejected",
    "Ghosted",
]

# Anthropic tool-calling schemas, one per function in src/agent/tools.py. This
# list is what the router node sends to Claude so it can decide which tool
# (if any) applies to a turn, and what arguments to call it with -- the
# `name` here is what Claude echoes back in its tool_use response, and is
# the key TOOL_REGISTRY below dispatches on.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "create_job_description",
        "description": "Save a pasted job description (company, role, full text) so it "
        "gets an id other tools can reference.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "role": {"type": "string"},
                "raw_text": {"type": "string", "description": "The full job description text."},
                "url": {"type": "string", "description": "Optional job posting URL."},
            },
            "required": ["company", "role", "raw_text"],
        },
    },
    {
        "name": "find_job_descriptions",
        "description": "Search previously saved job descriptions by company and/or role "
        "(case-insensitive partial match).",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "role": {"type": "string"},
            },
        },
    },
    {
        "name": "generate_cover_letter",
        "description": "Generate and compile a tailored cover letter (LaTeX + PDF) for a "
        "given resume and job description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "resume_id": {"type": "integer"},
                "job_id": {"type": "integer"},
            },
            "required": ["resume_id", "job_id"],
        },
    },
    {
        "name": "tailor_cv",
        "description": "Tailor the user's LaTeX CV template to a job description and "
        "compile it to PDF.",
        "input_schema": {
            "type": "object",
            "properties": {
                "resume_id": {"type": "integer"},
                "job_id": {"type": "integer"},
            },
            "required": ["resume_id", "job_id"],
        },
    },
    {
        "name": "score_match",
        "description": "Score how well a resume matches a job description (0.0-1.0) with "
        "a gap analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "resume_id": {"type": "integer"},
                "job_id": {"type": "integer"},
            },
            "required": ["resume_id", "job_id"],
        },
    },
    {
        "name": "get_application",
        "description": "Fetch one application by id, including every document generated "
        "for it.",
        "input_schema": {
            "type": "object",
            "properties": {"application_id": {"type": "integer"}},
            "required": ["application_id"],
        },
    },
    {
        "name": "update_status",
        "description": "Update an application's status and/or notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "integer"},
                "status": {"type": "string", "enum": _STATUS_ENUM},
                "notes": {"type": "string"},
            },
            "required": ["application_id", "status"],
        },
    },
    {
        "name": "list_applications",
        "description": "List applications, optionally filtered by status, company, "
        "and/or a minimum match score.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": _STATUS_ENUM},
                "company": {"type": "string"},
                "min_score": {"type": "number"},
            },
        },
    },
    {
        "name": "search_applications",
        "description": "Search applications by company name.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "parse_emails",
        "description": "Sync Gmail and auto-update application statuses from detected "
        "emails. Not yet configured.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

# Maps a tool name (as Claude will name it in a tool_use response) to the
# actual function in src/agent/tools.py that performs it. This is the single
# place that turns "the router decided on X" into "call the real X".
TOOL_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "create_job_description": tools.create_job_description_tool,
    "find_job_descriptions": tools.find_job_descriptions_tool,
    "generate_cover_letter": tools.generate_cover_letter_tool,
    "tailor_cv": tools.tailor_cv_tool,
    "score_match": tools.score_match_tool,
    "get_application": tools.get_application_tool,
    "update_status": tools.update_status_tool,
    "list_applications": tools.list_applications_tool,
    "search_applications": tools.search_applications_tool,
    "parse_emails": tools.parse_emails_tool,
}

ROUTER_SYSTEM_PROMPT = (
    "You are the routing brain for a job application assistant. Given the "
    "conversation so far, decide whether one of your tools should handle this "
    "turn, and if so, call exactly one tool with the correct arguments drawn "
    "from the conversation. IDs (resume_id, job_id, application_id) must be "
    "real numbers already mentioned in the conversation -- never invent one. "
    "If no tool applies -- the user is just chatting, asking a general "
    "question, or asking for something none of your tools do -- reply "
    "normally in plain text instead of calling a tool."
)


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
        "tool_call": None,
    }


def make_router_node(*, client: Any | None = None) -> Callable[[AgentState], dict[str, Any]]:
    """Build the router node: one Sonnet tool-calling request per turn decides
    whether a tool applies and, if so, which one and with what arguments.

    This is the "Router node: decides which tool node to activate" step from
    CLAUDE.md's architecture diagram, and the piece that actually reads
    `current_task`/`messages` with an LLM rather than just extracting text.
    `client` is injectable (same pattern as src/llm/clients.py's `generator`
    parameters) so tests can supply a fake Anthropic client instead of a real
    one.
    """
    def router_node(state: AgentState) -> dict[str, Any]:
        try:
            result = generate_with_anthropic_tools(
                state["messages"],
                tools=TOOL_SPECS,
                system=ROUTER_SYSTEM_PROMPT,
                client=client,
            )
        except Exception as exc:
            return {"tool_call": None, "error": str(exc)}

        if result["tool_call"] is None:
            return {
                "tool_call": None,
                "final_response": result["text"] or "I'm not sure how to help with that.",
            }
        return {"tool_call": result["tool_call"]}

    return router_node


def make_dispatch_executor(
    *, session_factory: Callable[[], Any] | None = None
) -> ToolExecutor:
    """Build the executor that runs whichever tool the router chose.

    Looks state["tool_call"] up in TOOL_REGISTRY, opens a short-lived DB
    session (mirroring the try/finally pattern already used throughout
    src/database/crud.py's callers), and calls that tool function with the
    router's arguments. `session_factory` is injectable, defaulting to the
    app's real `connection.SessionLocal`, so tests can supply a fake session.
    """
    def dispatch_executor(state: AgentState) -> dict[str, Any]:
        tool_call = state["tool_call"]
        if tool_call is None:
            raise ValueError("dispatch_executor called with no tool_call in state")
        tool_fn = TOOL_REGISTRY.get(tool_call["name"])
        if tool_fn is None:
            raise ValueError(f"Unknown tool: {tool_call['name']}")

        make_session = session_factory or connection.SessionLocal
        db = make_session()
        try:
            return tool_fn(db, **tool_call["args"])
        finally:
            db.close()

    return dispatch_executor


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

    response_node (or, on a direct conversational reply, the router itself)
    always runs immediately before this node, so state["final_response"] is
    guaranteed to be populated here. Without this append, the agent's own
    replies would never re-enter `messages`, so the next turn's LLM call
    would have no idea what it said last time.
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
