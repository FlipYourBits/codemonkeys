from __future__ import annotations

from codemonkeys.nodes.base import _split_allow


class TestSplitAllow:
    def test_bare_entries_fast_path_to_sdk(self):
        sdk, rules = _split_allow(["Read", "Glob", "Grep"], [])
        assert sdk == ["Read", "Glob", "Grep"]
        assert rules == []

    def test_patterned_entries_stay_in_rule_list(self):
        sdk, rules = _split_allow(["Bash(python*)", "Edit(*.py)"], [])
        assert sdk == []
        assert rules == ["Bash(python*)", "Edit(*.py)"]

    def test_mixed_entries_split_correctly(self):
        sdk, rules = _split_allow(["Read", "Bash(python*)", "Glob", "Edit(*.py)"], [])
        assert sdk == ["Read", "Glob"]
        assert rules == ["Bash(python*)", "Edit(*.py)"]

    def test_bare_entry_demoted_when_deny_mentions_same_tool(self):
        # Bash bare must run through can_use_tool so deny can win.
        sdk, rules = _split_allow(["Bash"], ["Bash(rm*)"])
        assert sdk == []
        assert rules == ["Bash"]

    def test_bare_entry_unaffected_by_unrelated_deny(self):
        sdk, rules = _split_allow(["Read", "Bash"], ["Edit(*.lock)"])
        assert sdk == ["Read", "Bash"]
        assert rules == []
