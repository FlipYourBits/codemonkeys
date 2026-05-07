from codemonkeys.dashboard.registry import discover_agents


def test_discover_finds_existing_agents():
    agents = discover_agents()
    names = [a.name for a in agents]
    assert "make_python_file_reviewer" in names
    assert "make_fixer" in names
    assert "make_review_auditor" in names


def test_agent_meta_has_description():
    agents = discover_agents()
    reviewer = next(a for a in agents if a.name == "make_python_file_reviewer")
    assert "Python files" in reviewer.description


def test_agent_meta_has_accepts():
    agents = discover_agents()
    reviewer = next(a for a in agents if a.name == "make_python_file_reviewer")
    assert reviewer.accepts == ["files"]
    fixer = next(a for a in agents if a.name == "make_fixer")
    assert reviewer.accepts != fixer.accepts


def test_agent_meta_has_default_model():
    agents = discover_agents()
    reviewer = next(a for a in agents if a.name == "make_python_file_reviewer")
    assert reviewer.default_model == "sonnet"
    fixer = next(a for a in agents if a.name == "make_fixer")
    assert fixer.default_model == "opus"
