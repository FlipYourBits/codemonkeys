from __future__ import annotations

from codemonkeys.core.prompts import DESIGN_REVIEW


class TestDesignReviewPrompt:
    def test_is_nonempty_string(self) -> None:
        assert isinstance(DESIGN_REVIEW, str)
        assert len(DESIGN_REVIEW) > 100

    def test_has_all_checklist_categories(self) -> None:
        expected_categories = [
            "paradigm_inconsistency",
            "communication_mismatch",
            "layer_violation",
            "responsibility_duplication",
            "dependency_coupling",
            "interface_inconsistency",
        ]
        for category in expected_categories:
            assert category in DESIGN_REVIEW, f"Missing category: {category}"

    def test_has_exclusions_section(self) -> None:
        assert "Exclusions" in DESIGN_REVIEW
