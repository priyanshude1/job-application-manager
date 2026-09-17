from src.agent import graph, state


def test_direct_conversational_reply():
    def fake_router(current_state):
        return {
            "tool_call": None,
            "final_response": "I can help with your applications.",
        }

    def unexpected_tool_call(current_state):
        raise AssertionError("The tool node should not run for a direct reply")

    agent = graph.build_graph(
        router_node=fake_router,
        tool_node=unexpected_tool_call,
    )
    initial_state = state.AgentState(
        messages=[{"role": "user", "content": "What can you help me with?"}],
        current_task="",
        tool_results=[],
        final_response="",
        error=None,
        tool_call=None,
        tool_call_count=0,
    )

    result = agent.invoke(initial_state)

    assert result["final_response"] == "I can help with your applications."
    assert result["messages"] == [
        {"role": "user", "content": "What can you help me with?"},
        {"role": "assistant", "content": "I can help with your applications."},
    ]
    assert result["tool_results"] == []
    assert result["tool_call_count"] == 0
    assert result["error"] is None


def test_agent_executes_one_tool():
	router_calls = []

	def fake_router(current_state):
		router_calls.append(current_state)
		if len(router_calls) == 2:
			return {
				"tool_call": None,
				"final_response": "The score was calculated successfully.",
			}
		return {
			"tool_call": {
				"name": "score_match",
				"args": {"resume_id": 1, "job_id": 2},
				"id": "tool-1",
			},
		}

	def fake_tool(current_state):
		return {
			"messages": [
				*current_state["messages"],
				{
					"role": "user",
					"content": [
						{
							"type": "tool_result",
							"tool_use_id": "tool-1",
							"content": "score calculated",
						}
					],
				},
			],
			"tool_results": [
				*current_state["tool_results"],
				{"success": True, "match_score": 0.85},
			],
			"tool_call_count": current_state["tool_call_count"] + 1,
		}

	agent = graph.build_graph(
		router_node=fake_router,
		tool_node=fake_tool,
	)
	initial_state = state.AgentState(
		messages=[{"role": "user", "content": "Score my resume."}],
		current_task="",
		tool_results=[],
		final_response="",
		error=None,
		tool_call=None,
		tool_call_count=0,
	)

	result = agent.invoke(initial_state)

	assert len(router_calls) == 2
	assert result["tool_results"] == [{"success": True, "match_score": 0.85}]
	assert result["tool_call_count"] == 1
	assert result["final_response"] == "The score was calculated successfully."
	assert result["messages"][-1] == {
		"role": "assistant",
		"content": "The score was calculated successfully.",
	}
	assert result["error"] is None
