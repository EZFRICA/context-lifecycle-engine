"""Measure the three test buckets of docs/TESTING.md instead of counting by hand.

The buckets say what a green suite does and does not prove about the production
vector space:

  1. embedder-agnostic   - no embedder ran for the test at all;
  2. stub-as-a-tool      - an embedder ran, but the claim is space-independent;
  3. stub-as-the-subject - the claim holds ONLY in `stub:hashed64`.

Buckets 1 and 2 are MEASURED. The suite runs once with an instrumentation probe
(`tests/conftest.py`, enabled by `CLE_BUCKET_REPORT`) that records which
embedder each test invoked - in its own body, in any fixture it depends on,
directly or transitively, and at the import of its module. A test that invoked
none is bucket 1; one that invoked any is bucket 2.

Bucket 3 is DECLARED, because "true only in the stub space" is a statement about
what the assertion means, which no probe can observe. It is declared by the
`stub_only` marker, and the declaration is CHECKED: a test marked `stub_only`
that never embedded in `stub:hashed64` is reported, since then the marker is
false.

A module's SCOPE header is checked the same way: a header naming a bucket that
the measurement contradicts is reported. Measurement is the authority; the
header is prose about it.

Usage:
    uv run python tools/buckets.py            # the table, plus disagreements
    uv run python tools/buckets.py --check    # exit 1 if docs/TESTING.md or a header disagrees
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUB = "stub:hashed64"
MEANINGS = {1: "embedder-agnostic", 2: "stub-as-a-tool", 3: "stub-as-the-subject"}

#: A SCOPE header declaring `stub:hashed64` ONLY is a bucket-3 declaration.
_STUB_ONLY_HEADER = re.compile(r"`stub:hashed64`\s+ONLY")
#: Case-insensitive: header prose starts sentences with "Bucket 1 for ...".
_BUCKET_WORD = re.compile(r"bucket\s+([123])", re.IGNORECASE)
_DOC_ROW = re.compile(r"^\|\s*\*\*([123])\.[^|]*\|\s*\*\*(\d+)\*\*\s*\|", re.M)


def classify(records: dict[str, dict], gated: tuple[str, ...] = ()
             ) -> tuple[dict[int, list[str]], list[str]]:
    """Bucket every recorded test; return the buckets and the contradictions.

    `records` maps a node id to `{"embedders": [...], "stub_only": bool}`.
    Tests under a `gated` path prefix are left out, exactly as the documented
    suite size leaves them out.
    """
    buckets: dict[int, list[str]] = {1: [], 2: [], 3: []}
    problems: list[str] = []
    for nodeid, record in sorted(records.items()):
        if any(nodeid.startswith(prefix) for prefix in gated):
            continue
        if record["stub_only"]:
            if STUB not in record["embedders"]:
                problems.append(f"{nodeid}: marked stub_only but never embedded in {STUB}")
            buckets[3].append(nodeid)
        elif record["embedders"]:
            buckets[2].append(nodeid)
        else:
            buckets[1].append(nodeid)
    return buckets, problems


def documented(testing_md: str) -> dict[int, int]:
    """The three counts as docs/TESTING.md states them in its bucket table."""
    return {int(b): int(n) for b, n in _DOC_ROW.findall(testing_md)}


def declared_buckets(module_source: str) -> set[int]:
    """The bucket(s) a test module's SCOPE header declares; empty when it declares none."""
    doc = module_source.split('"""')[1] if module_source.count('"""') >= 2 else ""
    scope = doc[doc.find("SCOPE"):] if "SCOPE" in doc else ""
    scope = scope.split("\n\n")[0]
    found = {int(n) for n in _BUCKET_WORD.findall(scope)}
    if _STUB_ONLY_HEADER.search(scope):
        found.add(3)
    return found


def header_disagreements(buckets: dict[int, list[str]], root: Path = ROOT) -> list[str]:
    measured: dict[str, set[int]] = defaultdict(set)
    for bucket, nodeids in buckets.items():
        for nodeid in nodeids:
            measured[nodeid.split("::")[0]].add(bucket)
    problems = []
    for module, found in sorted(measured.items()):
        declared = declared_buckets((root / module).read_text())
        if declared and not found <= declared:
            problems.append(f"{module}: header declares bucket(s) {sorted(declared)}, "
                            f"measured {sorted(found)}")
    return problems


def _gated() -> tuple[str, ...]:
    spec = importlib.util.spec_from_file_location(
        "_guards", ROOT / "tests" / "property" / "test_structural_guards.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return tuple(module.CORPUS_GATED)


def measure() -> dict[str, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "buckets.json"
        env = {**os.environ, "CLE_BUCKET_REPORT": str(report)}
        run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                             cwd=ROOT, env=env, capture_output=True, text=True)
        if run.returncode != 0:
            tail = "\n".join(run.stdout.splitlines()[-15:])
            raise SystemExit(f"the suite is not green; buckets are measured on a green run\n{tail}")
        return json.loads(report.read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="fail if docs/TESTING.md or a SCOPE header disagrees")
    args = parser.parse_args(argv)

    buckets, problems = classify(measure(), _gated())
    problems += header_disagreements(buckets)
    total = sum(len(v) for v in buckets.values())
    print(f"{'bucket':<26}{'tests':>6}")
    for bucket, nodeids in buckets.items():
        print(f"{bucket}. {MEANINGS[bucket]:<23}{len(nodeids):>6}")
    print(f"{'total':<26}{total:>6}")

    stated = documented((ROOT / "docs" / "TESTING.md").read_text())
    measured = {b: len(v) for b, v in buckets.items()}
    if stated != measured:
        problems.append(f"docs/TESTING.md states {stated}, measured {measured}")
    for problem in problems:
        print(f"  ! {problem}")
    return 1 if (args.check and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
