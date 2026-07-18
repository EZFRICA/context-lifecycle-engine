"""Invariant 3 — staged builds consume nothing.

Mandated test 4 of cle-core-contracts (test_staged_failure_writes_nothing),
written before the resolver exists. A failed stage leaves the store
byte-identical (snapshot compare) and burns zero trial occurrences; the
only permitted trace is the build log line.
"""

import io

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cle.build.resolver import ResolutionError, resolve
from cle.oplog import OpLog
from cle.store.backends import InMemoryStore
from cle.store.commits import SourceSpec
from cle.store.objects import Block


def _seeded_store(payloads: list[str]) -> tuple[InMemoryStore, list[str]]:
    store = InMemoryStore()
    hashes = []
    for payload in payloads:
        block = Block(kind="prompt_fragment", payload=payload)
        store.put(block.hash, block.canonical_bytes())
        hashes.append(block.hash)
    return store, hashes


@given(
    payloads=st.lists(st.text(min_size=1, max_size=32), min_size=0, max_size=4, unique=True),
    missing_name=st.text(
        alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=12
    ),
)
def test_staged_failure_writes_nothing(payloads: list[str], missing_name: str) -> None:
    store, _ = _seeded_store(payloads)
    before = store.snapshot()
    source = SourceSpec(
        yaml_raw=f"name: candidate\ncomponents:\n  - '#{missing_name}'\n"
    )
    with pytest.raises(ResolutionError):
        resolve(source, store, OpLog(io.StringIO()), actor="human:test")
    assert store.snapshot() == before


def test_malformed_yaml_fails_and_writes_nothing() -> None:
    store, _ = _seeded_store(["fragment"])
    before = store.snapshot()
    source = SourceSpec(yaml_raw="components: [unclosed")
    with pytest.raises(ResolutionError):
        resolve(source, store, OpLog(io.StringIO()), actor="human:test")
    assert store.snapshot() == before


def test_failed_resolve_logs_the_failing_stage() -> None:
    # The one permitted trace: a build line naming the stage that failed —
    # the raw material of the failure-stage distribution measurement.
    import json

    store, _ = _seeded_store([])
    sink = io.StringIO()
    source = SourceSpec(yaml_raw="name: c\ncomponents:\n  - '#missing'\n")
    with pytest.raises(ResolutionError):
        resolve(source, store, OpLog(sink), actor="human:test")
    lines = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert len(lines) == 1
    assert lines[0]["op"] == "build"
    assert lines[0]["stage"] == "resolve"
    assert lines[0]["outcome"] == "failed"
    assert "latency_ms" in lines[0]
