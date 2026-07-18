"""Resolver behavior: both ref forms resolve; failures are fast and typed."""

import io

import pytest

from cle.build.resolver import ResolutionError, resolve
from cle.oplog import OpLog
from cle.store.backends import InMemoryStore
from cle.store.commits import SourceSpec
from cle.store.objects import Block


def test_resolves_hash_refs_and_named_refs() -> None:
    store = InMemoryStore()
    block = Block(kind="prompt_fragment", payload="recap format")
    store.put(block.hash, block.canonical_bytes())
    store.move_ref("blocks/recap_format", block.hash)

    source = SourceSpec(
        yaml_raw=(
            "name: weekly_recap\n"
            "components:\n"
            f"  - '#{block.hash}'\n"
            "  - '#blocks/recap_format'\n"
        )
    )
    sink = io.StringIO()
    resolved = resolve(source, store, OpLog(sink), actor="human:test")
    assert resolved == {
        f"#{block.hash}": block.hash,
        "#blocks/recap_format": block.hash,
    }
    # A successful stage logs nothing — the pipeline owns the single
    # success line for the whole build.
    assert sink.getvalue() == ""


def test_corrupt_component_fails_resolve_and_fires_integrity_log() -> None:
    # BLUEPRINT §8 tamper line, driven through resolve itself: corrupt a
    # stored component -> resolve fails typed, integrity log fires, store
    # unchanged, and exactly one build line names the stage.
    import json

    from cle.store.objects import IntegrityError

    store = InMemoryStore()
    block = Block(kind="prompt_fragment", payload="recap format")
    store.put(block.hash, block.canonical_bytes())
    store._objects[block.hash] = block.canonical_bytes() + b"tampered"

    before = store.snapshot()
    sink = io.StringIO()
    source = SourceSpec(yaml_raw=f"name: c\ncomponents:\n  - '#{block.hash}'\n")
    with pytest.raises(IntegrityError):
        resolve(source, store, OpLog(sink), actor="human:test")

    assert store.snapshot() == before
    ops = [json.loads(line)["op"] for line in sink.getvalue().splitlines()]
    assert ops.count("integrity_violation") >= 1
    assert ops.count("build") == 1
    build_line = [
        json.loads(line) for line in sink.getvalue().splitlines()
    ][ops.index("build")]
    assert build_line["stage"] == "resolve" and build_line["outcome"] == "failed"


def test_missing_ref_error_names_every_missing_ref() -> None:
    store = InMemoryStore()
    source = SourceSpec(
        yaml_raw="name: c\ncomponents:\n  - '#gone'\n  - '#also/gone'\n"
    )
    with pytest.raises(ResolutionError) as excinfo:
        resolve(source, store, OpLog(io.StringIO()), actor="human:test")
    assert excinfo.value.missing_refs == ("#also/gone", "#gone")


def test_named_ref_pointing_at_missing_object_fails() -> None:
    # A dangling ref (name exists, target object gone) is a resolution
    # failure, not a crash.
    store = InMemoryStore()
    block = Block(kind="prompt_fragment", payload="x")
    store.put(block.hash, block.canonical_bytes())
    store.move_ref("blocks/x", block.hash)
    store._objects.clear()  # simulate the object vanishing under the ref

    source = SourceSpec(yaml_raw="name: c\ncomponents:\n  - '#blocks/x'\n")
    with pytest.raises(ResolutionError):
        resolve(source, store, OpLog(io.StringIO()), actor="human:test")


def test_components_must_be_a_list_of_refs() -> None:
    store = InMemoryStore()
    for bad_yaml in [
        "name: c\n",  # no components at all
        "name: c\ncomponents: notalist\n",
        "name: c\ncomponents:\n  - noleadinghash\n",
        "- just\n- a\n- list\n",  # not a mapping
    ]:
        with pytest.raises(ResolutionError):
            resolve(SourceSpec(yaml_raw=bad_yaml), store, OpLog(io.StringIO()), actor="human:test")
