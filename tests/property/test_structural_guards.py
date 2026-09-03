"""Structural guards over the repository itself.

SCOPE — bucket 1 (embedder-agnostic): these assert properties of the source
tree, not of any vector space.

CLE need. Verifying something once and guarding it are not the same thing, and
only one of the two survives. Each test here converts a whole CLASS of defect,
not one instance, into something that fails on its own.

  * §1 single writer  — invariant 1 of the blueprint (`topology.yaml` has one
    writer) had ZERO test representation. Opening a second write site inside
    `OpLog.emit`, the hottest path in the system, and the suite stayed green.
  * §2 cited files    — 2 of the 7 "names that designate nothing" were file
    names cited in docstrings: `temperature_experiment.py`, offered as PROOF of
    invariant 6 and never written, and `WeaviateStore`. Both were found by
    reading, not by failing.
  * §3 suite count    — the published test count drifts every time a test file
    is added, and a stale count in the README is the first thing a reader sees.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGES = (ROOT / "cle", ROOT / "dashboard")


# ── §1 topology.yaml has exactly one writer ─────────────────────────────────

#: The one module allowed to write the topology artifact.
TOPOLOGY_WRITER = "cle/lifecycle/topology.py"


def _topology_write_sites() -> list[str]:
    """Files containing a write to a path whose name is `topology.yaml`.

    Matches `<expr>.write_text(...)` where the receiver mentions `topology`, and
    any literal "topology.yaml" appearing next to a write call — deliberately
    broad, because a guard that only knows today's spelling is the grep-audit
    failure again.
    """
    sites = []
    for package in PACKAGES:
        for path in sorted(package.rglob("*.py")):
            source = path.read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Attribute):
                    continue
                if func.attr not in ("write_text", "write_bytes", "safe_dump", "dump"):
                    continue
                segment = ast.get_source_segment(source, node) or ""
                context = source[max(0, node.lineno - 400) : node.lineno + 400]
                if "topology" in segment.lower() or "topology.yaml" in context:
                    sites.append(str(path.relative_to(ROOT)))
    return sorted(set(sites))


def test_topology_yaml_has_exactly_one_writer() -> None:
    sites = _topology_write_sites()
    assert sites == [TOPOLOGY_WRITER], (
        f"topology.yaml write sites: {sites}, expected only [{TOPOLOGY_WRITER!r}]. "
        "Invariant 1: the lifecycle engine is the single writer — it is what makes "
        "the topology history a trustworthy channel for a population level."
    )


def test_the_declared_writer_actually_writes() -> None:
    # Guards the guard: if topology.py stopped writing, the assertion above
    # would pass vacuously on an empty list.
    assert TOPOLOGY_WRITER in _topology_write_sites()


# ── §2 every file name cited in a docstring exists ──────────────────────────

#: `word.ext` with an extension we ship. Bare module refs (`engine.py`) count;
#: prose like "v1" or "3.5" does not.
_CITED = re.compile(r"[\w./*-]+\.(?:py|sh|json|ya?ml|md|jsonl|toml|css|js|html)\b")

#: Names that are patterns, or artifacts the system CREATES at runtime rather
#: than files that ship. Each exemption is named individually — a broadened
#: regex would quietly re-admit the phantoms this guard exists to catch.
_NOT_A_PATH = {
    "vectors.*.json",        # a glob over the cache family
    "examples/vectors.*.json",
    "settings.local.json",   # may be absent on a fresh clone
    # FileStore's on-disk layout. Present only after a FileStore run, and absent
    # entirely when the state dir uses SqliteStore — so its absence says which
    # backend last ran, not that the docstring lies.
    "refs.json",
}


def _cited_file_names() -> list[tuple[str, str]]:
    """(citing file, cited name) for every file name inside a docstring."""
    cited = []
    for package in PACKAGES:
        for path in sorted(package.rglob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(
                    node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    continue
                doc = ast.get_docstring(node)
                if not doc:
                    continue
                for name in _CITED.findall(doc):
                    if name in _NOT_A_PATH or "*" in name:
                        continue
                    cited.append((str(path.relative_to(ROOT)), name))
    return cited


def _exists(name: str) -> bool:
    if (ROOT / name).exists():
        return True
    # A bare basename may live anywhere in the tree.
    base = Path(name).name
    return any(ROOT.glob(f"**/{base}"))


def test_every_file_cited_in_a_docstring_exists() -> None:
    missing = sorted({(src, name) for src, name in _cited_file_names() if not _exists(name)})
    assert not missing, (
        f"docstrings cite files that do not exist: {missing}. "
        "A docstring citing a nonexistent file is the pattern this codebase keeps "
        "reproducing — `temperature_experiment.py` was offered as PROOF of an "
        "invariant that measurement later contradicted."
    )


def test_the_citation_scrape_sees_something() -> None:
    # Without this, a broken regex would make the guard pass on an empty set.
    assert len(_cited_file_names()) > 10


# ── §3 the published test count matches the collected one ───────────────────

# Every doc that states a suite size. Reorganising the documentation is how a
# file drops off this list: `docs/TESTING.md` was carved out of CAPABILITIES.md
# and the tuple was not extended, leaving the one file whose entire subject is
# the test count free to drift.
#
# The list is enumerated rather than globbed on purpose: a glob would silently
# start or stop covering a file when docs are reorganised, which is the failure
# above with an extra step. Adding a doc that states a count means adding it
# here, and the test below explains why when it fails.
DOCS_WITH_COUNTS = (
    "README.md",
    "docs/CAPABILITIES.md",
    "docs/METRICS.md",
    "docs/TESTING.md",
)
_COUNT = re.compile(r"\*\*(\d+)[ -]tests?\b|\*\*(\d+) tests across (\d+) files")


def _collected() -> tuple[int, int]:
    """(tests, files) straight from pytest's own collector."""
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout
    rows = re.findall(r"^(tests/\S+\.py): (\d+)$", out, re.M)
    return sum(int(n) for _, n in rows), len(rows)


@pytest.mark.parametrize("doc", DOCS_WITH_COUNTS)
def test_the_documented_test_count_matches_reality(doc: str) -> None:
    """The docs must state the suite size, and state it correctly.

    Deliberately indifferent to HOW a doc phrases it: what matters is that no
    number presented as the suite size contradicts the collector.
    """
    path = ROOT / doc
    if not path.exists():
        pytest.skip(f"{doc} not present")
    tests, files = _collected()
    text = path.read_text()
    claimed = {int(m) for m in re.findall(r"\*\*(\d+) tests\b", text)}
    claimed |= {int(m) for m in re.findall(r"\*\*(\d+)-test\b", text)}

    # The check above is vacuous on a doc whose count no longer PARSES. A
    # botched edit ("**324 37 tests across  files**") matches neither pattern,
    # so `claimed` comes back empty and the guard passes on a doc that now
    # states nothing, which is a green suite over a doc that says nothing.
    #
    #
    # So the guard is two-directional now: the doc must state a count, AND the
    # count must be right. Silence is a failure, not a pass.
    assert claimed, (
        f"{doc} is listed in DOCS_WITH_COUNTS but states no parseable test count. "
        "Either the number was mangled by an edit (which silently disables this "
        "guard), or the doc no longer states one and should leave the tuple."
    )

    wrong = sorted(c for c in claimed if c != tests)
    assert not wrong, (
        f"{doc} claims {wrong} tests; the collector reports {tests} across {files} files. "
        "This number has drifted six times — the guard exists so it cannot drift again."
    )
