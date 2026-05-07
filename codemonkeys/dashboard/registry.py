"""Agent registry — discovers agent factories via introspection."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass, field

import codemonkeys.agents as agents_pkg
from codemonkeys.core.types import AgentDefinition


@dataclass(frozen=True)
class AgentMeta:
    """Metadata about a registered agent factory."""

    name: str
    description: str
    accepts: list[str] = field(default_factory=list)
    default_model: str = "sonnet"
    produces: str | None = None


def _infer_accepts(sig: inspect.Signature) -> list[str]:
    """Infer input type from the first parameter's type annotation."""
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls", "model"):
            continue
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            return ["unknown"]
        ann_str = str(annotation)
        if "str" in ann_str and "list" in ann_str.lower():
            return ["files"]
        if "FixItem" in ann_str:
            return ["findings"]
        if "RunResult" in ann_str:
            return ["run_result"]
        return ["unknown"]
    return ["unknown"]


def discover_agents() -> list[AgentMeta]:
    """Scan codemonkeys.agents and return metadata for all factory functions."""
    agents: list[AgentMeta] = []

    for module_info in pkgutil.iter_modules(agents_pkg.__path__):
        module = importlib.import_module(f"codemonkeys.agents.{module_info.name}")

        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            obj = getattr(module, attr_name)
            if not callable(obj) or inspect.isclass(obj):
                continue

            sig = inspect.signature(obj)
            if sig.return_annotation not in (AgentDefinition, "AgentDefinition"):
                ret_str = str(sig.return_annotation)
                if "AgentDefinition" not in ret_str:
                    continue

            description = (inspect.getdoc(obj) or "").split("\n")[0]
            accepts = _infer_accepts(sig)

            default_model = "sonnet"
            if "model" in sig.parameters:
                model_param = sig.parameters["model"]
                if model_param.default is not inspect.Parameter.empty:
                    default_model = model_param.default

            agents.append(
                AgentMeta(
                    name=attr_name,
                    description=description,
                    accepts=accepts,
                    default_model=default_model,
                )
            )

    return sorted(agents, key=lambda a: a.name)
