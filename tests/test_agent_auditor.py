from __future__ import annotations

from codemonkeys.core.agents.agent_auditor import make_agent_auditor, AGENT_SOURCES


class TestAgentAuditorFactory:
    def test_returns_agent_definition(self):
        agent = make_agent_auditor("codemonkeys/core/agents/changelog_reviewer.py")
        assert agent.description
        assert agent.model == "sonnet"
        assert "Read" in agent.tools
        assert agent.permissionMode == "dontAsk"

    def test_embeds_source_path_in_prompt(self):
        path = "codemonkeys/core/agents/readme_reviewer.py"
        agent = make_agent_auditor(path)
        assert path in agent.prompt

    def test_prompt_instructs_evaluation(self):
        agent = make_agent_auditor("codemonkeys/core/agents/changelog_reviewer.py")
        assert "instruction compliance" in agent.prompt.lower() or "instruction" in agent.prompt.lower()
        assert "tool" in agent.prompt.lower()
        assert "efficiency" in agent.prompt.lower() or "turn" in agent.prompt.lower()

    def test_agent_sources_registry_has_known_agents(self):
        assert "python_file_reviewer" in AGENT_SOURCES
        assert "changelog_reviewer" in AGENT_SOURCES
        assert "architecture_reviewer" in AGENT_SOURCES

    def test_agent_sources_paths_exist(self):
        from pathlib import Path
        for name, path in AGENT_SOURCES.items():
            assert Path(path).exists(), f"Agent source for {name} not found: {path}"
