from codemonkeys.agents.review_auditor import ReviewAudit, make_review_auditor


def test_make_review_auditor_returns_definition():
    agent = make_review_auditor(
        trace="[0.0s] TOOL: Read(a.py)",
        findings_json='{"results": []}',
        reviewer_name="python_file_reviewer:a.py",
        reviewer_model="sonnet",
        reviewer_tools="Read, Grep",
        reviewer_prompt="You review code.",
    )
    assert agent.name.startswith("auditor:")
    assert agent.model == "sonnet"
    assert agent.output_schema is ReviewAudit
    assert agent.tools == []


def test_make_review_auditor_prompt_contains_trace():
    agent = make_review_auditor(
        trace="[0.0s] TOOL: Read(a.py)\n       RESULT: contents",
        findings_json='{"results": []}',
        reviewer_name="reviewer",
        reviewer_model="sonnet",
        reviewer_tools="Read, Grep",
        reviewer_prompt="You review code.",
    )
    assert "TOOL: Read(a.py)" in agent.system_prompt
    assert "RESULT: contents" in agent.system_prompt


def test_make_review_auditor_prompt_contains_reviewer_config():
    agent = make_review_auditor(
        trace="(empty trace)",
        findings_json="null",
        reviewer_name="python_file_reviewer:a.py",
        reviewer_model="haiku",
        reviewer_tools="Read, Grep",
        reviewer_prompt="You review Python files.",
    )
    assert "python_file_reviewer:a.py" in agent.system_prompt
    assert "haiku" in agent.system_prompt
    assert "Read, Grep" in agent.system_prompt
    assert "You review Python files." in agent.system_prompt


def test_make_review_auditor_custom_model():
    agent = make_review_auditor(
        trace="(empty)",
        findings_json="null",
        reviewer_name="r",
        reviewer_model="sonnet",
        reviewer_tools="Read",
        reviewer_prompt="prompt",
        model="opus",
    )
    assert agent.model == "opus"
