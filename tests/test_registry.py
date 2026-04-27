from __future__ import annotations

import pytest

from langclaude.registry import (
    list_builtins,
    list_registered,
    register,
    resolve,
)


@pytest.fixture(autouse=True)
def _clean_user_registry():
    from langclaude import registry as reg

    snapshot = dict(reg._USER_REGISTRY)
    yield
    reg._USER_REGISTRY.clear()
    reg._USER_REGISTRY.update(snapshot)


class TestBuiltins:
    def test_known_builtins_exist(self):
        builtins = list_builtins()
        expected = {
            "new_branch",
            "implement_feature",
            "code_review",
            "security_audit",
            "docs_review",
            "ruff_fix",
            "ruff_fmt",
            "pytest",
            "coverage",
            "dependency_audit",
        }
        assert expected == set(builtins)

    def test_resolve_builtin(self):
        factory = resolve("ruff_fix")
        assert callable(factory)

    def test_resolve_unknown_raises(self):
        with pytest.raises(KeyError, match="no_such_node"):
            resolve("no_such_node")


class TestUserRegistry:
    def test_register_and_resolve(self):
        async def my_node(state):
            return {}

        register("deploy", my_node, namespace="acme")
        resolved = resolve("acme/deploy")
        assert resolved is my_node

    def test_register_default_namespace(self):
        async def my_node(state):
            return {}

        register("lint", my_node)
        resolved = resolve("custom/lint")
        assert resolved is my_node

    def test_register_name_with_slash_raises(self):
        with pytest.raises(ValueError, match="must not contain"):
            register("bad/name", lambda s: {})

    def test_resolve_unknown_user_node_raises(self):
        with pytest.raises(KeyError, match="not found in user registry"):
            resolve("custom/nonexistent")

    def test_list_registered(self):
        register("alpha", lambda s: {}, namespace="test")
        register("beta", lambda s: {}, namespace="test")
        registered = list_registered()
        assert "test/alpha" in registered
        assert "test/beta" in registered
