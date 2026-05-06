"""Static analysis via ast — deterministic metadata extraction for architecture review."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FunctionInfo:
    name: str
    is_async: bool
    args: list[dict[str, str | None]]
    return_type: str | None
    decorators: list[str]


@dataclass
class ClassInfo:
    name: str
    bases: list[str]
    decorators: list[str]
    methods: list[FunctionInfo]


@dataclass
class FileAnalysis:
    file: str
    imports: list[dict[str, str | list[str] | None]]
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    error: str | None = None


def analyze_file(path: str, *, root: Path | None = None) -> FileAnalysis:
    """Extract structural metadata from a Python file using ast.

    Returns a FileAnalysis with imports, top-level functions, and classes.
    If the file cannot be parsed, returns a FileAnalysis with the error field set.
    """
    try:
        full_path = Path(path) if root is None else root / path
        source = full_path.read_text()
        tree = ast.parse(source, filename=path)
    except (SyntaxError, OSError) as exc:
        return FileAnalysis(file=path, imports=[], error=str(exc))

    imports = _extract_imports(tree)
    functions = _extract_functions(tree)
    classes = _extract_classes(tree)

    return FileAnalysis(
        file=path,
        imports=imports,
        functions=functions,
        classes=classes,
    )


def analyze_files(files: list[str], *, root: Path | None = None) -> list[FileAnalysis]:
    """Analyze multiple files. Errors in individual files don't stop the batch."""
    return [analyze_file(f, root=root) for f in files]


def format_analysis(analyses: list[FileAnalysis]) -> str:
    """Format analyses as compact text suitable for an LLM prompt."""
    sections: list[str] = []
    for analysis in analyses:
        lines = [f"### `{analysis.file}`"]
        if analysis.error:
            lines.append(f"  Parse error: {analysis.error}")
            sections.append("\n".join(lines))
            continue

        if analysis.imports:
            lines.extend(_format_imports(analysis.imports))

        for fn in analysis.functions:
            lines.append(_format_function(fn, indent="  "))

        for cls in analysis.classes:
            lines.extend(_format_class(cls))

        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _format_imports(imports: list[dict[str, str | list[str] | None]]) -> list[str]:
    internal: list[str] = []
    external: list[str] = []
    for imp in imports:
        module = imp["module"] or ""
        names = imp["names"]
        label = f"{module}({', '.join(names)})" if names else module
        if "." in module and not module.startswith(("os.", "json.", "sys.")):
            internal.append(label)
        else:
            external.append(label)
    lines: list[str] = []
    if internal:
        lines.append(f"  Internal imports: {', '.join(internal)}")
    if external:
        lines.append(f"  External imports: {', '.join(external)}")
    return lines


def _format_function(fn: FunctionInfo, indent: str) -> str:
    prefix = "async " if fn.is_async else ""
    args = ", ".join(
        f"{arg['name']}: {arg['type']}" if arg["type"] else arg["name"]
        for arg in fn.args
        if arg["name"] != "self"
    )
    ret = f" -> {fn.return_type}" if fn.return_type else ""
    deco = "".join(f"@{d} " for d in fn.decorators)
    return f"{indent}{deco}{prefix}{fn.name}({args}){ret}"


def _format_class(cls: ClassInfo) -> list[str]:
    bases = f"({', '.join(cls.bases)})" if cls.bases else ""
    deco = "".join(f"@{d} " for d in cls.decorators)
    lines = [f"  {deco}class {cls.name}{bases}:"]
    for m in cls.methods:
        if m.name == "__init__":
            init_args = ", ".join(
                f"{arg['name']}: {arg['type']}" if arg["type"] else arg["name"]
                for arg in m.args
                if arg["name"] != "self"
            )
            lines.append(f"    __init__({init_args})")
        else:
            lines.append(_format_function(m, indent="    "))
    return lines


def _extract_imports(tree: ast.Module) -> list[dict[str, str | list[str] | None]]:
    imports: list[dict[str, str | list[str] | None]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({"module": alias.name, "names": None})
        elif isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names]
            imports.append({"module": node.module or "", "names": names})
    return imports


def _extract_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> FunctionInfo:
    args = []
    for arg in node.args.args:
        ann = ast.unparse(arg.annotation) if arg.annotation else None
        args.append({"name": arg.arg, "type": ann})
    return FunctionInfo(
        name=node.name,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        args=args,
        return_type=ast.unparse(node.returns) if node.returns else None,
        decorators=[ast.unparse(d) for d in node.decorator_list],
    )


def _extract_functions(tree: ast.Module) -> list[FunctionInfo]:
    return [
        _extract_function(node)
        for node in ast.iter_child_nodes(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]


def _extract_classes(tree: ast.Module) -> list[ClassInfo]:
    classes = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                _extract_function(item)
                for item in node.body
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
            classes.append(
                ClassInfo(
                    name=node.name,
                    bases=[ast.unparse(b) for b in node.bases],
                    decorators=[ast.unparse(d) for d in node.decorator_list],
                    methods=methods,
                )
            )
    return classes
