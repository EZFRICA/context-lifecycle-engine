"""Every shipped script must at least resolve its own names.

SCOPE: bucket 1 (embedder-agnostic). Nothing here executes a script, opens a
network connection, or costs anything: it reads the AST.

CLE need. `examples/bigquery/space_identity.py` called `bqconfig.project()`
without ever importing `bqconfig`. It crashed with `NameError` on the line that
builds the BigQuery client, before the billed query, and stayed broken because
running it costs money so nobody ran it casually. `docs/BIGQUERY.md` cites it as
the reproduction command for a published figure, so the figure had no working
command behind it.

The whole class is cheap to catch: a module-level name that is loaded but never
bound is a `NameError` waiting for whoever runs the file. This finds it without
executing anything, which is the only way a guard over billed scripts can run in
an offline suite.

Deliberately module scope only. Names inside functions can legitimately come
from a closure, a global assigned later, or an argument, and chasing those needs
real scope analysis; the defect this exists for was at module level, and staying
there keeps the check honest rather than approximate.
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIRS = (ROOT / "examples", ROOT / "tools")

BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__"}


def _scripts() -> list[Path]:
    found: list[Path] = []
    for directory in SCRIPT_DIRS:
        for path in sorted(directory.rglob("*.py")):
            if any(part in ("data", "states", "__pycache__") for part in path.parts):
                continue
            found.append(path)
    return found


def _module_level_bindings(tree: ast.Module) -> set[str]:
    """Names a module binds at its own top level.

    Recurses through control flow (`for`, `if`, `while`, `with`, `try`) because a
    module-level `for` loop body binds module-level names, but stops at function
    and class bodies, which open their own scope. Missing that recursion reports
    every loop variable in a script as unbound, which is a checker that cries
    wolf and therefore gets deleted.
    """
    bound: set[str] = set()

    def visit(statements: list[ast.stmt]) -> None:
        for node in statements:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    bound.add(alias.asname or alias.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)          # its body is another scope
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    bound.update(_targets(target))
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                bound.update(_targets(node.target))
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                bound.update(_targets(node.target))
                visit(node.body); visit(node.orelse)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if item.optional_vars is not None:
                        bound.update(_targets(item.optional_vars))
                visit(node.body)
            elif isinstance(node, (ast.If, ast.While)):
                visit(node.body); visit(node.orelse)
            elif isinstance(node, ast.Try):
                for handler in node.handlers:
                    if handler.name:
                        bound.add(handler.name)
                    visit(handler.body)
                visit(node.body); visit(node.orelse); visit(node.finalbody)

    visit(tree.body)
    return bound


def _targets(node: ast.expr) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in node.elts:
            names |= _targets(element)
        return names
    return set()


def _module_level_loads(tree: ast.Module) -> set[str]:
    """Names read at module level, outside any function or class body.

    Comprehensions and lambdas bind their own names in their own scope, so those
    bindings are collected across the whole subtree FIRST and subtracted at the
    end. Subtracting them as they are walked does not work: a target can be
    read before its own comprehension node is reached, and the set would keep a
    name that is perfectly well bound.
    """
    loads: set[str] = set()
    inner_bindings: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load):
                loads.add(inner.id)
            elif isinstance(inner, (ast.ListComp, ast.SetComp, ast.DictComp,
                                    ast.GeneratorExp)):
                for generator in inner.generators:
                    inner_bindings |= _targets(generator.target)
            elif isinstance(inner, ast.Lambda):
                inner_bindings |= {a.arg for a in inner.args.args}
                inner_bindings |= {a.arg for a in inner.args.kwonlyargs}
                if inner.args.vararg:
                    inner_bindings.add(inner.args.vararg.arg)
                if inner.args.kwarg:
                    inner_bindings.add(inner.args.kwarg.arg)
            elif isinstance(inner, ast.NamedExpr):
                inner_bindings |= _targets(inner.target)
    return loads - inner_bindings


@pytest.mark.parametrize("script", _scripts(), ids=lambda p: str(p.relative_to(ROOT)))
def test_every_module_level_name_is_bound(script: Path) -> None:
    tree = ast.parse(script.read_text())
    bound = _module_level_bindings(tree)
    unbound = sorted(
        name for name in _module_level_loads(tree)
        if name not in bound and name not in BUILTINS
    )
    assert not unbound, (
        f"{script.relative_to(ROOT)} reads {unbound} at module level without "
        "binding them. This is a NameError the next person to run the script "
        "will hit, and for a billed script that person may be paying to find it."
    )


def test_the_scrape_sees_the_scripts() -> None:
    # Without this, a broken glob would make every assertion above vacuous.
    assert len(_scripts()) > 20
