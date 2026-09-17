import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.agent import graph
from src.agent import state

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None

class ChatResponse(BaseModel):
    response: str
    session_id: str

sessions: dict[str, list[dict]] = {}

agent_graph = graph.build_graph()

@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions:
        sessions[session_id] = []
    
    message = {"role": "user", "content": request.message}
    sessions[session_id].append(message)
    init_state = state.AgentState(
        messages = sessions[session_id],
        current_task="",
        tool_results=[],
        final_response="",
        error = None,
        tool_call = None,
        tool_call_count = 0,
    )


    try: 
        result = agent_graph.invoke(init_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")

    sessions[session_id] = result["messages"]

    return ChatResponse(response=result["final_response"], session_id=session_id)


@router.get("/chat/sessions")
def list_sessions():
    return {"sessions": list(sessions.keys())}

@router.delete("/chat/sessions/{session_id}")
def delete_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
        return {"detail": f"Session {session_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail="Session not found")

