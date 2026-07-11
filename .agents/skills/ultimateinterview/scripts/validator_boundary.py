#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["typer>=0.12"]
# ///

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath
from typing import Annotated, Final, NamedTuple, override

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)
IMPORT_PREFIXES: Final[frozenset[str]] = frozenset(
    {"subprocess", "asyncio.subprocess", "multiprocessing", "pty", "socket", "http", "urllib", "requests", "httpx", "importlib", "boto3", "google.cloud.storage", "google.resumable_media", "azure.storage.blob"}
)
CALL_PREFIXES: Final[tuple[str, ...]] = (
    "os.system", "os.exec", "os.popen", "os.spawn", "subprocess", "asyncio.create_subprocess", "asyncio.subprocess",
    "multiprocessing.Process", "multiprocessing.Pool", "pty.spawn", "socket.socket", "http.client", "urllib", "requests", "httpx", "importlib.import_module",
)
REFLECTION_GADGETS: Final[frozenset[str]] = frozenset({"operator.attrgetter", "operator.itemgetter", "operator.methodcaller"})
DYNAMIC_CALLS: Final[frozenset[str]] = frozenset({"__import__", "eval", "exec", "compile", "getattr", "setattr", "delattr", "hasattr", "globals", "locals", "vars"})
REFLECTION_SEGMENTS: Final[frozenset[str]] = frozenset({"__call__", "__dict__", "__getattribute__", "__builtins__", "__globals__", "__subclasses__", "gi_frame", "cr_frame", "f_builtins"})
MODULE_REGISTRY_PREFIX: Final[str] = "sys.modules"
LEGACY_EXCEPTIONS: Final[frozenset[str]] = frozenset(
    {".agents/skills/ultimateinterview/scripts/regression_check.py", ".agents/skills/ultimateinterview-postmortem/scripts/capture_verification.py"}
)


class ChangedPath(NamedTuple):
    relative: str
    absolute: Path


def _matches(qualified: str, prefixes: tuple[str, ...] | frozenset[str]) -> bool:
    return any(qualified == prefix or qualified.startswith(f"{prefix}.") for prefix in prefixes)


def _forbidden_call(qualified: str) -> bool:
    normalized = qualified.removeprefix("builtins.")
    return normalized in DYNAMIC_CALLS or qualified in REFLECTION_GADGETS or _matches(qualified, CALL_PREFIXES) or _process_api(qualified) or bool(REFLECTION_SEGMENTS & set(qualified.split(".")))


def _forbidden_import(qualified: str) -> bool:
    return _matches(qualified, IMPORT_PREFIXES) or qualified in REFLECTION_GADGETS or _process_api(qualified)


def _process_api(qualified: str) -> bool:
    return _matches(qualified, ("os.system", "os.popen")) or qualified.startswith(("os.exec", "os.spawn"))


def _module_registry_reflection(qualified: str) -> bool:
    return qualified == MODULE_REGISTRY_PREFIX or qualified.startswith(f"{MODULE_REGISTRY_PREFIX}.")


def read_changed_paths(workspace_root: Path, changed_paths: Path) -> tuple[tuple[ChangedPath, ...], tuple[str, ...]]:
    root = workspace_root.resolve()
    paths: list[ChangedPath] = []
    diagnostics: list[str] = []
    seen: set[str] = set()
    content = changed_paths.read_text(encoding="utf-8")
    if not content:
        return (), ("invalid-changed-path: blank",)
    for raw in content.splitlines():
        if not raw.strip():
            diagnostics.append("invalid-changed-path: blank")
            continue
        parts = raw.split("/")
        if "\\" in raw or raw.startswith("/") or ".." in parts:
            diagnostics.append(f"invalid-changed-path: escaping: {raw}")
            continue
        if any(not part or part == "." for part in parts):
            diagnostics.append(f"invalid-changed-path: noncanonical: {raw}")
            continue
        candidate = PurePosixPath(raw)
        if candidate.is_absolute():
            diagnostics.append(f"invalid-changed-path: escaping: {raw}")
            continue
        relative = candidate.as_posix()
        if relative in seen:
            diagnostics.append(f"invalid-changed-path: duplicate: {relative}")
            continue
        seen.add(relative)
        source = root / relative
        if source.suffix == ".py" and source.is_symlink():
            diagnostics.append(f"symlink-changed-path: {relative}")
            continue
        target = source.resolve()
        if not target.is_relative_to(root):
            diagnostics.append(f"invalid-changed-path: escaping: {relative}")
        elif not target.is_file():
            diagnostics.append(f"missing-changed-path: {relative}")
        else:
            paths.append(ChangedPath(relative, target))
    return tuple(paths), tuple(diagnostics)


def _qualified(node: ast.expr, aliases: dict[str, str]) -> str | None:
    match node:
        case ast.Name(id=name):
            return aliases.get(name, name)
        case ast.Lambda():
            return "<lambda>"
        case ast.Attribute(value=value, attr=attribute):
            base = _qualified(value, aliases)
            return f"{base}.{attribute}" if base else None
        case ast.Subscript(value=value, slice=ast.Constant(value=str() as key)):
            base = _qualified(value, aliases)
            return f"{base}.{key}" if base else None
        case _:
            return None


class _ForbiddenVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}
        self.diagnostics: list[str] = []

    @override
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.aliases[alias.asname or alias.name.split(".")[0]] = alias.name
            if _forbidden_import(alias.name):
                self.diagnostics.append(f"forbidden-import: {alias.name}")

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            qualified = f"{module}.{alias.name}" if module else alias.name
            self.aliases[alias.asname or alias.name] = qualified
            if alias.name == "*":
                self.diagnostics.append(f"forbidden-import: {module}.*")
            elif _forbidden_import(qualified):
                self.diagnostics.append(f"forbidden-import: {qualified}")

    def _bind(self, target: ast.expr, qualified: str | None) -> None:
        match target:
            case ast.Name(id=name):
                if qualified is None:
                    _ = self.aliases.pop(name, None)
                else:
                    self.aliases[name] = qualified
            case ast.Tuple(elts=elements) | ast.List(elts=elements):
                for element in elements:
                    self._bind(element, None)
            case _:
                pass

    def _record_reference(self, node: ast.expr) -> None:
        qualified = _qualified(node, self.aliases)
        if qualified and _module_registry_reflection(qualified):
            self.diagnostics.append(f"forbidden-reflection: {qualified}")
        elif qualified and _forbidden_call(qualified):
            self.diagnostics.append(f"forbidden-call: {qualified}")

    @override
    def visit_Attribute(self, node: ast.Attribute) -> None:
        self._record_reference(node)
        self.generic_visit(node)

    @override
    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._record_reference(node)
        self.generic_visit(node)

    @override
    def visit_Assign(self, node: ast.Assign) -> None:
        qualified = _qualified(node.value, self.aliases)
        for target in node.targets:
            self._bind(target, qualified)
        self.generic_visit(node)

    @override
    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._bind(node.target, _qualified(node.value, self.aliases) if node.value else None)
        self.generic_visit(node)

    @override
    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._bind(node.target, _qualified(node.value, self.aliases))
        self.generic_visit(node)

    def _visit_scope(self, node: ast.AST) -> None:
        outer = self.aliases
        self.aliases = dict(outer)
        self.generic_visit(node)
        self.aliases = outer

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scope(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_scope(node)

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scope(node)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        qualified = _qualified(node.func, self.aliases)
        if qualified and _module_registry_reflection(qualified):
            self.diagnostics.append(f"forbidden-reflection: {qualified}")
        elif qualified and _forbidden_call(qualified):
            self.diagnostics.append(f"forbidden-call: {qualified}")
        self.generic_visit(node)


def _production_path(path: ChangedPath) -> bool:
    return "/scripts/" in f"/{path.relative}" and path.absolute.suffix == ".py" and not path.absolute.name.startswith("test_") and path.relative not in LEGACY_EXCEPTIONS


def validate(workspace_root: Path, changed_paths: Path) -> tuple[str, ...]:
    paths, diagnostics = read_changed_paths(workspace_root, changed_paths)
    results = list(diagnostics)
    for path in paths:
        if not _production_path(path):
            continue
        try:
            tree = ast.parse(path.absolute.read_text(encoding="utf-8"), filename=path.relative)
        except SyntaxError:
            results.append(f"invalid-python: {path.relative}")
            continue
        visitor = _ForbiddenVisitor()
        visitor.visit(tree)
        results.extend(visitor.diagnostics)
    return tuple(sorted(set(results)))


@app.command()
def main(
    workspace_root: Annotated[Path, typer.Option("--workspace-root")],
    changed_paths: Annotated[Path, typer.Option("--changed-paths")],
) -> None:
    diagnostics = validate(workspace_root, changed_paths)
    if diagnostics:
        typer.echo("\n".join(diagnostics))
        raise typer.Exit(1)
    typer.echo("validator-boundary: ok")


if __name__ == "__main__":
    app()
