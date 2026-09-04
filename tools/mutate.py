"""Mutation harness: does a guard actually bite, or is it only documented?

An exception class named in a test file proves nothing about the raise site you
care about. `SpaceMismatchError` has three raise sites; a test naming it may
cover one. A guard described at length in the documentation may be reachable by
no test at all. The only way to know is to remove the guard and see what goes
red.

This runs that experiment for every `raise` in a subtree, and reports which test
goes red per site.

FOUR WAYS TO GET THIS WRONG, all of them silent, all handled here:

1. **`pass` before a `raise` neutralises nothing.** `pass` is a no-op and the
   `raise` still runs, so the mutation is inert and every verdict it produces is
   noise. `mutate_source` REPLACES the raise statement, located by AST offsets,
   and `tests/unit/test_mutation_harness.py` executes the mutant to prove it no
   longer raises.

2. **A syntactically broken mutant reads as a passing guard.** pytest reports a
   collection failure as `ERROR`, not `FAILED`, so a filter counting only
   `FAILED` sees "this guard does not bite" when the truth is "this tool broke
   the file". The mutant is `ast.parse`d BEFORE the suite runs, and `ERROR` is
   counted and reported SEPARATELY as a harness failure, never as a finding.

3. **A file left mutated poisons every later measurement.** Restoration is
   verified by hash, and a signal handler drains an in-flight registry, because
   a `finally` does not survive SIGTERM arriving during the inner pytest run.

4. **A suite that is not green before the sweep makes every guard look
   enforced.** One unrelated failing test means every site sees a red suite and
   is scored as "the mutation bit". The suite runs ONCE unmutated first, and
   those baseline failures are subtracted from every verdict; a non-empty
   baseline is reported loudly, because a sweep over a red suite measures
   nothing.

Usage:

    python tools/mutate.py                  # every raise site in cle/ + dashboard/
    python tools/mutate.py cle/detect       # one subtree
    python tools/mutate.py --list           # sites only, no suite runs
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Marker left in the mutant. Distinctive so a leaked one is greppable.
MARKER = "pass  # MUTATED-BY-tools/mutate.py"

#: Guards whose removal is expected NOT to break the suite are still reported;
#: this tool never decides that an unguarded raise is acceptable.
DEFAULT_TARGETS = ("cle", "dashboard")


@dataclass(frozen=True)
class Site:
    """One `raise` statement, addressable and mutable."""

    path: Path
    line: int
    exception: str

    def __str__(self) -> str:
        return f"{self.path.relative_to(ROOT)}:{self.line} {self.exception}"


@dataclass(frozen=True)
class Verdict:
    """What happened when one site was neutralised."""

    site: Site
    bites: bool
    failed: tuple[str, ...]
    errored: tuple[str, ...]
    harness_broke: bool
    note: str = ""


def _exception_name(node: ast.Raise) -> str:
    exc = node.exc
    if exc is None:
        return "bare-raise"
    call = exc.func if isinstance(exc, ast.Call) else exc
    if isinstance(call, ast.Name):
        return call.id
    if isinstance(call, ast.Attribute):
        return call.attr
    return "unknown"


def find_raise_sites(path: Path) -> list[Site]:
    """Every `raise` statement in one file, by AST rather than by grep.

    Grep cannot tell `raise X(` in code from the same text in a docstring, and
    this campaign has already published a measurement that counted the latter.
    """
    tree = ast.parse(path.read_text())
    return [
        Site(path=path, line=node.lineno, exception=_exception_name(node))
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
    ]


def _offset(source: str, line: int, col: int) -> int:
    lines = source.splitlines(keepends=True)
    return sum(len(x) for x in lines[: line - 1]) + col


def mutate_source(source: str, line: int) -> str:
    """Replace the `raise` statement starting at `line` so it cannot raise.

    REPLACES, never precedes. The statement is located by the AST's own
    start/end offsets, so a multi-line raise with a formatted message and a
    trailing `from None` is removed whole; a textual substitution would leave
    the `from None` orphaned, which is mistake 2.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.lineno == line:
            start = _offset(source, node.lineno, node.col_offset)
            end = _offset(source, node.end_lineno, node.end_col_offset)
            return source[:start] + MARKER + source[end:]
    raise LookupError(f"no raise statement begins at line {line}")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_suite(extra: list[str] | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Run pytest and split FAILED from ERROR.

    They mean different things and conflating them is mistake 2: a FAILED is a
    guard doing its job, an ERROR is this tool having broken the tree.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
         *(extra or [])],
        cwd=ROOT, capture_output=True, text=True,
    )
    return classify_output(proc.stdout)


def classify_output(stdout: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(failed, errored) test ids from a pytest short summary."""
    failed = tuple(re.findall(r"^FAILED (\S+)", stdout, re.M))
    errored = tuple(re.findall(r"^ERROR (\S+)", stdout, re.M))
    if "SyntaxError" in stdout and not errored:
        errored = errored + ("<syntax-error>",)
    return failed, errored


#: Excluded from the verdict: it depends on the documented count, not on the
#: guard under test, so it goes red for reasons unrelated to the mutation.
IRRELEVANT = "test_the_documented_test_count"


#: path -> original source, for every file currently mutated. A `finally` alone
#: does NOT survive SIGTERM arriving while the inner pytest runs, which leaves a
#: production file mutated and every later measurement wrong. The signal handler
#: below restores from here.
_IN_FLIGHT: dict[Path, str] = {}


def restore_all() -> list[Path]:
    """Put every in-flight file back. Safe to call twice."""
    restored = []
    for path, original in list(_IN_FLIGHT.items()):
        path.write_text(original)
        restored.append(path)
        _IN_FLIGHT.pop(path, None)
    return restored


def _on_signal(signum, _frame):
    restored = restore_all()
    print(f"\ninterrupted; restored {len(restored)} file(s): "
          f"{', '.join(str(p.name) for p in restored) or 'none'}", flush=True)
    raise SystemExit(130)


def install_signal_handlers() -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _on_signal)


def baseline_failures(extra: list[str] | None = None) -> tuple[str, ...]:
    """Tests already failing BEFORE anything is mutated.

    Without this the sweep credits every guard with a failure it did not cause,
    and reports a flattering number that is pure artefact.
    """
    failed, _ = _run_suite(extra)
    return tuple(f for f in failed if IRRELEVANT not in f)


def check_site(site: Site, *, extra: list[str] | None = None,
               baseline: tuple[str, ...] = ()) -> Verdict:
    """Neutralise one site, run the suite, restore, verify the restore."""
    original = site.path.read_text()
    before = _digest(site.path)
    _IN_FLIGHT[site.path] = original
    try:
        mutant = mutate_source(original, site.line)
        try:
            ast.parse(mutant)                      # mistake 2, caught before the suite
        except SyntaxError as error:
            return Verdict(site, False, (), ("<mutant-not-parseable>",), True, str(error))
        if MARKER not in mutant or mutant == original:
            return Verdict(site, False, (), ("<mutation-was-a-no-op>",), True,
                           "the source is unchanged; the raise was not replaced")
        site.path.write_text(mutant)
        failed, errored = _run_suite(extra)
        failed = tuple(f for f in failed
                       if IRRELEVANT not in f and f not in baseline)
        return Verdict(site, bool(failed), failed, errored, bool(errored))
    finally:
        site.path.write_text(original)
        _IN_FLIGHT.pop(site.path, None)
        if _digest(site.path) != before:           # mistake 3
            raise RuntimeError(f"failed to restore {site.path}; the tree is now dirty")


def collect(targets: list[str]) -> list[Site]:
    sites: list[Site] = []
    for target in targets:
        base = ROOT / target
        files = [base] if base.is_file() else sorted(base.rglob("*.py"))
        for path in files:
            sites.extend(find_raise_sites(path))
    return sites


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", default=list(DEFAULT_TARGETS))
    parser.add_argument("--list", action="store_true", help="list sites, run nothing")
    parser.add_argument("-k", dest="expr", help="pass -k to the inner pytest run")
    args = parser.parse_args(argv)

    install_signal_handlers()
    sites = collect(args.targets or list(DEFAULT_TARGETS))
    if args.list:
        for site in sites:
            print(f"  {site}")
        print(f"\n{len(sites)} raise sites")
        return 0

    extra = ["-k", args.expr] if args.expr else None

    baseline = baseline_failures(extra)
    if baseline:
        print("!! THE SUITE IS NOT GREEN BEFORE THE SWEEP. These tests already "
              "fail and are subtracted from every verdict; fix them first, "
              "because a sweep over a red suite measures nothing:", flush=True)
        for test in baseline:
            print(f"     {test}", flush=True)
        print(flush=True)

    unguarded, broken = [], []
    print(f"{len(sites)} raise sites\n", flush=True)
    for site in sites:
        verdict = check_site(site, extra=extra, baseline=baseline)
        if verdict.harness_broke:
            broken.append(verdict)
            mark, detail = "HARNESS", verdict.errored[0]
        elif verdict.bites:
            mark, detail = "bites", verdict.failed[0].split("::")[-1]
        else:
            unguarded.append(verdict)
            mark, detail = "UNGUARDED", ""
        print(f"  {mark:10} {str(verdict.site):64} {detail[:46]}", flush=True)

    print(f"\nguarded {len(sites) - len(unguarded) - len(broken)}/{len(sites)}"
          f"   unguarded {len(unguarded)}   harness failures {len(broken)}")
    for verdict in broken:
        print(f"  HARNESS FAILURE (not a finding): {verdict.site} {verdict.note[:80]}")
    return 1 if unguarded or broken else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
