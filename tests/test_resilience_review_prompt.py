from __future__ import annotations

from codemonkeys.core.prompts import RESILIENCE_REVIEW


class TestResilienceReviewPrompt:
    def test_is_nonempty_string(self) -> None:
        assert isinstance(RESILIENCE_REVIEW, str)
        assert len(RESILIENCE_REVIEW) > 100

    def test_has_all_checklist_categories(self) -> None:
        expected_categories = [
            "concurrency",
            "error_recovery",
            "log_hygiene",
        ]
        for category in expected_categories:
            assert category in RESILIENCE_REVIEW, f"Missing category: {category}"

    def test_has_exclusions_section(self) -> None:
        assert "Exclusions" in RESILIENCE_REVIEW

    def test_mentions_asyncio_gather(self) -> None:
        assert "asyncio.gather" in RESILIENCE_REVIEW

    def test_mentions_timeout(self) -> None:
        assert "timeout" in RESILIENCE_REVIEW.lower()

    def test_mentions_log_level(self) -> None:
        assert (
            "log level" in RESILIENCE_REVIEW.lower()
            or "log_level" in RESILIENCE_REVIEW.lower()
        )
