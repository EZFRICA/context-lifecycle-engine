"""`tools/mutate.py` has to be right before it can judge anything else.

SCOPE: bucket 1 (embedder-agnostic). Nothing here runs a suite or touches a
vector space; these tests pin the harness's pure functions.

Each test names the way of getting mutation testing wrong that it prevents. All
four are silent: they produce a verdict that looks like a result, and three of
the four produce the flattering direction, so they survive being read.
"""

from __future__ import annotations

import ast
import textwrap

import pytest

from tools.mutate import (
    MARKER,
    classify_output,
    find_raise_sites,
    mutate_source,
)

GUARDED = textwrap.dedent('''
    class Refused(ValueError):
        """A test-local exception."""

    def check(value):
        """Docstring mentioning `raise Refused(...)`, which is NOT a site."""
        if value < 0:
            raise Refused(
                f"negative: {value}. A multi-line message, because the real "
                "ones are multi-line and that is where textual substitution "
                "breaks."
            )
        return value
''')

CHAINED = textwrap.dedent('''
    def lookup(mapping, key):
        try:
            return mapping[key]
        except KeyError:
            raise LookupError(f"no {key!r}") from None
''')


# ── mistake 1: `pass` BEFORE a raise neutralises nothing ────────────────────

def test_the_mutant_actually_stops_raising() -> None:
    """Not "the text changed" but "the behaviour changed".

    The mutant is executed and must return instead of raising. A `pass` inserted
    BEFORE the raise passes a textual check and fails this one, which is why the
    harness replaces the statement rather than preceding it.
    """
    line = find_raise_sites_in(GUARDED)[0].line
    mutant = mutate_source(GUARDED, line)

    original_ns: dict = {}
    exec(compile(GUARDED, "<original>", "exec"), original_ns)
    with pytest.raises(original_ns["Refused"]):
        original_ns["check"](-1)

    mutant_ns: dict = {}
    exec(compile(mutant, "<mutant>", "exec"), mutant_ns)
    # NOT "returns None": removing the raise lets control fall through to the
    # normal return, so the mutant answers -1. What matters is that nothing is
    # raised, which is exactly what a suite run would then observe.
    assert mutant_ns["check"](-1) == -1, (
        "the mutant still raises, so a suite run against it would prove nothing"
    )


def test_a_prepended_pass_would_not_have_worked() -> None:
    """Pins the reasoning, not just the fix.

    An executable statement of why the harness replaces rather than precedes, so
    the shortcut cannot be reintroduced as an optimisation.
    """
    naive = GUARDED.replace("            raise Refused(",
                            "            pass\n            raise Refused(")
    namespace: dict = {}
    exec(compile(naive, "<naive>", "exec"), namespace)
    with pytest.raises(namespace["Refused"]):
        namespace["check"](-1)


# ── mistake 2: a broken mutant reads as a passing guard ─────────────────────

def test_a_chained_raise_is_removed_whole() -> None:
    """`raise X(...) from None` is where textual substitution breaks.

    Replacing only `raise X(` leaves `) from None` orphaned. The AST offsets
    cover the whole statement, so the mutant parses.
    """
    line = find_raise_sites_in(CHAINED)[0].line
    mutant = mutate_source(CHAINED, line)
    ast.parse(mutant)                       # would raise SyntaxError before the fix
    assert "from None" not in mutant
    assert MARKER in mutant


def test_errors_are_reported_separately_from_failures() -> None:
    """An ERROR is the harness breaking; a FAILED is a guard working.

    Counting only FAILED turns a broken mutant into a "this guard does not bite"
    verdict, which is the wrong finding reported with confidence.
    """
    stdout = (
        "FAILED tests/unit/test_a.py::test_one - AssertionError\n"
        "ERROR tests/unit/test_b.py - SyntaxError: invalid syntax\n"
    )
    failed, errored = classify_output(stdout)
    assert failed == ("tests/unit/test_a.py::test_one",)
    assert errored == ("tests/unit/test_b.py",)


def test_a_bare_syntax_error_is_not_silently_clean() -> None:
    # A collection failure that prints no ERROR line still must not read as
    # "nothing failed, so the guard is unguarded".
    _, errored = classify_output("E   SyntaxError: invalid syntax\n")
    assert errored, "a SyntaxError with no ERROR line was treated as a clean run"


# ── the site finder ────────────────────────────────────────────────────────

def test_a_docstring_mentioning_raise_is_not_a_site() -> None:
    """Grep counts prose; the AST does not.

    `check`'s docstring names `raise Refused(...)`. A grep-based site count
    reports two sites here and then reports one of them as unguardable.
    """
    assert len(find_raise_sites_in(GUARDED)) == 1


def test_the_exception_name_is_recovered() -> None:
    assert find_raise_sites_in(GUARDED)[0].exception == "Refused"
    assert find_raise_sites_in(CHAINED)[0].exception == "LookupError"


def test_mutating_a_line_with_no_raise_is_an_error_not_a_no_op() -> None:
    # Silence here would restore the file and report "does not bite", which is
    # an inert mutation wearing a different hat.
    with pytest.raises(LookupError):
        mutate_source(GUARDED, 1)


# ── helper ─────────────────────────────────────────────────────────────────

def find_raise_sites_in(source: str):
    """`find_raise_sites` takes a path; these fixtures are strings."""
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkdtemp()) / "sample.py"
    path.write_text(source)
    return find_raise_sites(path)


# ── mistake 3, the one the tool committed itself ───────────────────────────

def test_restore_all_puts_an_in_flight_file_back(tmp_path) -> None:
    """`finally` does not survive a signal.

    A sweep stopped with SIGTERM while the inner pytest is running leaves the
    production file mutated, and that poisons every later measurement silently:
    the mutant still parses and the suite still mostly passes.

    The registry is what the signal handler drains, so this test drives the
    registry rather than the `finally`.
    """
    from tools import mutate

    victim = tmp_path / "victim.py"
    original = "def f():\n    raise ValueError('x')\n"
    victim.write_text(original)

    mutate._IN_FLIGHT[victim] = original
    victim.write_text(mutate.mutate_source(original, 2))
    assert mutate.MARKER in victim.read_text()

    restored = mutate.restore_all()

    assert restored == [victim]
    assert victim.read_text() == original
    assert not mutate._IN_FLIGHT, "a second signal would re-write stale content"
    assert mutate.restore_all() == [], "restore_all must be safe to call twice"


# ── mistake 4: a red suite makes every guard look enforced ─────────────────

def test_baseline_failures_are_subtracted_from_a_verdict(monkeypatch, tmp_path) -> None:
    """A verdict must be computed against what was ALREADY failing.

    One unrelated failing test makes every mutation see a red suite, so every
    site is scored as "the mutation bit". The resulting number is pure artefact
    in the flattering direction, which is how such a number survives being read.
    """
    from tools import mutate

    victim = tmp_path / "victim.py"
    original = "def f(x):\n    if x < 0:\n        raise ValueError('neg')\n    return x\n"
    victim.write_text(original)
    site = mutate.find_raise_sites(victim)[0]

    # The suite "fails" identically with and without the mutation: one unrelated
    # test is red for its own reasons.
    monkeypatch.setattr(mutate, "_run_suite",
                        lambda extra=None: (("tests/unit/test_unrelated.py::test_x",), ()))

    without = mutate.check_site(site)
    assert without.bites, "sanity: with no baseline the stale failure is credited"

    baseline = ("tests/unit/test_unrelated.py::test_x",)
    with_baseline = mutate.check_site(site, baseline=baseline)
    assert not with_baseline.bites, (
        "a failure that predates the mutation was credited to the guard"
    )
    assert victim.read_text() == original
