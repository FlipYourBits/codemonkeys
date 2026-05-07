# tests/test_pipeline.py
"""Tests for functional pipeline helpers."""

from __future__ import annotations

from codemonkeys.core.pipeline import chunked


class TestChunked:
    def test_even_split(self):
        assert chunked([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]

    def test_uneven_split(self):
        assert chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

    def test_single_chunk(self):
        assert chunked([1, 2, 3], 10) == [[1, 2, 3]]

    def test_size_one(self):
        assert chunked([1, 2, 3], 1) == [[1], [2], [3]]

    def test_empty(self):
        assert chunked([], 3) == []
