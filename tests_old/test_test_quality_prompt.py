from __future__ import annotations

from codemonkeys.core.prompts import TEST_QUALITY


class TestTestQualityPrompt:
    def test_is_nonempty_string(self) -> None:
        assert isinstance(TEST_QUALITY, str)
        assert len(TEST_QUALITY) > 100

    def test_has_all_checklist_categories(self) -> None:
        expected_categories = [
            "assertion_quality",
            "test_design",
            "isolation",
        ]
        for category in expected_categories:
            assert category in TEST_QUALITY, f"Missing category: {category}"

    def test_has_exclusions_section(self) -> None:
        assert "Exclusions" in TEST_QUALITY

    def test_mentions_tautological(self) -> None:
        assert "tautological" in TEST_QUALITY.lower() or "assert True" in TEST_QUALITY

    def test_mentions_mock(self) -> None:
        assert "mock" in TEST_QUALITY.lower()
