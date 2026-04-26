from __future__ import annotations

from langclaude.nodes.test_coverage import _condense_ranges


class TestCondenseRanges:
    def test_empty(self):
        assert _condense_ranges([]) == []

    def test_single(self):
        assert _condense_ranges([5]) == [(5, 5)]

    def test_contiguous(self):
        assert _condense_ranges([1, 2, 3, 4]) == [(1, 4)]

    def test_gaps(self):
        assert _condense_ranges([1, 2, 3, 7, 8]) == [(1, 3), (7, 8)]

    def test_unsorted_with_dups(self):
        assert _condense_ranges([3, 1, 2, 3, 7]) == [(1, 3), (7, 7)]
