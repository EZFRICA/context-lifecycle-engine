"""Inventory the repo's behavioural claims, and say which ones a test enforces.

A repository states more than it enforces. This script turns that into a ratio
instead of an impression.

TWO POPULATIONS, and the difference between them is the whole point.

**Enforceable mechanically.** A claim that names an exception has a raise site,
and `tools/mutate.py` decides by experiment whether removing it turns the suite
red. Nothing here is opinion: the verdict is a suite run.

**Not enforceable mechanically.** "The store is append-only", "one writer",
"never crash", "always logs one line". These are real claims and some of them
have real tests, but no script can decide which test covers which sentence.
This tool counts them and prints them; it deliberately does NOT guess a mapping,
because a guessed mapping is itself an unchecked reference, which is the thing
being measured.

So the headline is two numbers, not one:

    exception-bearing claims : N, of which M proven enforced by mutation
    prose claims             : P, mapping is manual and is not attempted here

Usage:
    python tools/statements.py            # the ratio and the prose list
    python tools/statements.py --prose    # the prose claims, with locations
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = ("cle", "dashboard")
DOCS = ("README.md", "docs")

#: Phrasings that assert a behaviour rather than describe one. Deliberately
#: narrow: a wide net would inflate the denominator and make the ratio flattering
#: in the wrong direction. Each pattern is a claim a reader would expect a test
#: to back.
CLAIM = re.compile(
    r"\b("
    r"is (?:refused|rejected|required|guaranteed|forbidden|enforced)"
    r"|are (?:refused|rejected|required|guaranteed|forbidden|enforced)"
    r"|(?:can|must) never"
    r"|never (?:writes|reads|returns|raises|silently|a verdict)"
    r"|always (?:computed|logs|carries)"
    r"|must (?:stay|carry|be|not)"
    r"|cannot (?:be|change|flow|end up)"
    r"|only (?:one|the engine|meaningful)"
    r"|exactly one"
    r"|one-way"
    r"|no (?:test|silent|fallback)"
    r"|raises\b"
    r")",
    re.IGNORECASE,
)

#: A claim naming one of these is mechanically checkable: it has raise sites.
EXCEPTION = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:Error|Exception))\b")


@dataclass(frozen=True)
class Claim:
    where: str
    text: str
    exception: str | None


def _sentences(blob: str) -> list[str]:
    flat = " ".join(blob.split())
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", flat) if s.strip()]


def from_docstrings() -> list[Claim]:
    claims: list[Claim] = []
    for root in CODE:
        for path in sorted((ROOT / root).rglob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Module, ast.ClassDef,
                                         ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                doc = ast.get_docstring(node)
                if not doc:
                    continue
                name = getattr(node, "name", "<module>")
                line = getattr(node, "lineno", 1)   # ast.Module has none
                for sentence in _sentences(doc):
                    if CLAIM.search(sentence):
                        found = EXCEPTION.search(sentence)
                        claims.append(Claim(
                            f"{path.relative_to(ROOT)}:{line} {name}",
                            sentence, found.group(1) if found else None,
                        ))
    return claims


def from_docs() -> list[Claim]:
    claims: list[Claim] = []
    paths: list[Path] = []
    for entry in DOCS:
        target = ROOT / entry
        paths.extend([target] if target.is_file() else sorted(target.glob("*.md")))
    for path in paths:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.startswith(("|", "```", "    ")):
                continue                       # tables and code blocks are not prose
            for sentence in _sentences(line):
                if CLAIM.search(sentence):
                    found = EXCEPTION.search(sentence)
                    claims.append(Claim(
                        f"{path.relative_to(ROOT)}:{number}",
                        sentence, found.group(1) if found else None,
                    ))
    return claims


def raise_sites_by_exception() -> dict[str, int]:
    from tools.mutate import collect

    counts: dict[str, int] = {}
    for site in collect(list(CODE)):
        counts[site.exception] = counts.get(site.exception, 0) + 1
    return counts


def tests_naming(exception: str) -> int:
    """How many test FILES name this exception. NOT a coverage measure.

    The contrast is the point: three test files can name `SpaceMismatchError`
    while two of its three raise sites are unguarded. Naming is not covering,
    and printing both columns makes that visible.
    """
    return sum(
        1 for path in (ROOT / "tests").rglob("*.py")
        if exception in path.read_text()
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prose", action="store_true",
                        help="print the prose claims with their locations")
    args = parser.parse_args(argv)

    claims = from_docstrings() + from_docs()
    with_exception = [c for c in claims if c.exception]
    prose = [c for c in claims if not c.exception]

    sites = raise_sites_by_exception()
    named = sorted({c.exception for c in with_exception if c.exception})

    print(f"claims inventoried            : {len(claims)}")
    print(f"  naming an exception         : {len(with_exception)}   "
          f"({len(named)} distinct exceptions)")
    print(f"  prose, no exception named   : {len(prose)}\n")

    print(f"{'exception':34}{'raise sites':>12}{'test files naming it':>22}")
    for exception in named:
        print(f"{exception:34}{sites.get(exception, 0):>12}{tests_naming(exception):>22}")

    orphan = [e for e in named if not sites.get(e)]
    if orphan:
        print("\nNAMED IN PROSE BUT NEVER RAISED (the docs describe a guard that "
              "does not exist):")
        for exception in orphan:
            print(f"  {exception}")

    print(f"\nrun `python tools/mutate.py` for the enforcement verdict per site; "
          f"naming counts above are NOT coverage.")

    if args.prose:
        print(f"\n{len(prose)} prose claims. No mapping is attempted: see the "
              f"module docstring.\n")
        for claim in prose:
            print(f"  {claim.where}\n      {claim.text[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
