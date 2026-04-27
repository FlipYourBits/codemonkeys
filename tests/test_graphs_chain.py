"""Tests for graphs/__init__.py chain helper — sub-chain fan-out and edge cases."""

from __future__ import annotations

import asyncio

from langgraph.graph import StateGraph

from langclaude.graphs import _connect, _register, _register_chain, chain


def _echo_node(key: str):
    """Return a sync node that writes key to state."""

    def node(state):
        return {**state, key: "done"}

    return node


class TestRegister:
    def test_tuple_adds_node(self):
        g = StateGraph(dict)
        name = _register(g, ("mynode", _echo_node("mynode")))
        assert name == "mynode"

    def test_string_passes_through(self):
        g = StateGraph(dict)
        name = _register(g, "__start__")
        assert name == "__start__"


class TestRegisterChain:
    def test_registers_sequential_sub_chain(self):
        g = StateGraph(dict)
        names = _register_chain(
            g,
            [
                ("a", _echo_node("a")),
                ("b", _echo_node("b")),
            ],
        )
        assert names == ["a", "b"]


class TestConnect:
    def test_single_to_single(self):
        g = StateGraph(dict)
        g.add_node("a", _echo_node("a"))
        g.add_node("b", _echo_node("b"))
        _connect(g, "a", "b")

    def test_list_to_list(self):
        g = StateGraph(dict)
        g.add_node("a", _echo_node("a"))
        g.add_node("b", _echo_node("b"))
        g.add_node("c", _echo_node("c"))
        g.add_node("d", _echo_node("d"))
        _connect(g, ["a", "b"], ["c", "d"])


class TestChainWithSubChains:
    def test_parallel_with_sub_chain_compiles(self):
        """Sub-list within a parallel group compiles without error."""
        g = StateGraph(dict)
        chain(
            g,
            ("first", _echo_node("first")),
            [
                ("par_a", _echo_node("par_a")),
                [("sub1", _echo_node("sub1")), ("sub2", _echo_node("sub2"))],
            ],
            ("last", _echo_node("last")),
        )
        app = g.compile()
        assert app is not None

    def test_simple_chain_runs(self):
        g = StateGraph(dict)
        chain(
            g,
            ("a", _echo_node("a")),
            ("b", _echo_node("b")),
        )
        app = g.compile()
        result = asyncio.get_event_loop().run_until_complete(
            app.ainvoke({"input": "go"})
        )
        assert result["a"] == "done"
        assert result["b"] == "done"
