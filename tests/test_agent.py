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


def test_agent_stops_after_three_tools():
	router_calls = []

	def fake_router(current_state):
		router_calls.append(current_state)
		tool_number = len(router_calls)
		tools = [
			{
				"id": "tool-1",
				"name": "create_job_description",
				"args": {
					"company": "Google",
					"role": "SDE1",
					"raw_text": "Qualifications Required: Masters in CS",
				},
			},
			{
				"id": "tool-2",
				"name": "tailor_cv",
				"args": {"resume_id": 5, "job_id": 7},
			},
			{
				"id": "tool-3",
				"name": "generate_cover_letter",
				"args": {"resume_id": 5, "job_id": 7},
			},
		]
		return {"tool_call": tools[tool_number - 1]}

	def fake_tool(current_state):
		tool_call = current_state["tool_call"]
		tool_result = {
			"success": True,
			"tool_name": tool_call["name"],
		}
		return {
			"messages": [
				*current_state["messages"],
				{
					"role": "user",
					"content": [
						{
							"type": "tool_result",
							"tool_use_id": tool_call["id"],
							"content": tool_call["name"] + " completed",
						}
					],
				},
			],
			"tool_results": [*current_state["tool_results"], tool_result],
			"tool_call_count": current_state["tool_call_count"] + 1,
		}

	agent = graph.build_graph(
		router_node=fake_router,
		tool_node=fake_tool,
	)
	initial_state = state.AgentState(
		messages=[{"role": "user", "content": "Prepare my application."}],
		current_task="",
		tool_results=[],
		final_response="",
		error=None,
		tool_call=None,
		tool_call_count=0,
	)

	result = agent.invoke(initial_state)

	assert len(router_calls) == 3
	assert result["tool_call_count"] == 3
	assert [item["tool_name"] for item in result["tool_results"]] == [
		"create_job_description",
		"tailor_cv",
		"generate_cover_letter",
	]
	assert result["final_response"] == str(result["tool_results"][-1])
	assert result["error"] is None


def test_agent_reports_router_error():
	def failing_router(current_state):
		return {"tool_call": None, "error": "Anthropic unavailable"}

	def unexpected_tool_call(current_state):
		raise AssertionError("The tool node should not run when routing fails")

	agent = graph.build_graph(
		router_node=failing_router,
		tool_node=unexpected_tool_call,
	)
	initial_state = state.AgentState(
		messages=[{"role": "user", "content": "List my applications."}],
		current_task="",
		tool_results=[],
		final_response="",
		error=None,
		tool_call=None,
		tool_call_count=0,
	)

	result = agent.invoke(initial_state)

	assert result["final_response"] == (
		"I couldn't complete that request: Anthropic unavailable"
	)
	assert result["messages"][-1] == {
		"role": "assistant",
		"content": "I couldn't complete that request: Anthropic unavailable",
	}
	assert result["tool_results"] == []
	assert result["error"] == "Anthropic unavailable"


def test_agent_reports_tool_error():
	def fake_router(current_state):
		return {
			"tool_call": {
				"id": "tool-error",
				"name": "score_match",
				"args": {"resume_id": 1, "job_id": 2},
			}
		}

	def failing_tool(current_state):
		return {"error": "Resume or job description not found"}

	agent = graph.build_graph(
		router_node=fake_router,
		tool_node=failing_tool,
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

	assert result["final_response"] == (
		"I couldn't complete that request: Resume or job description not found"
	)
	assert result["messages"][-1] == {
		"role": "assistant",
		"content": (
			"I couldn't complete that request: Resume or job description not found"
		),
	}
	assert result["tool_results"] == []
	assert result["error"] == "Resume or job description not found"

