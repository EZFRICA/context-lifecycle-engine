"""Mandated tests 1 and 6 — two-hash inequality and build determinism.

Written against the full three-stage pipeline: same source + same resolved
components + same fingerprint => same image hash; and the image hash can
never equal the source hash.
"""

import io
from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from cle.build import build_image
from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.episodes import DetectorConfig, Message
from cle.oplog import OpLog
from cle.store.backends import InMemoryStore
from cle.store.objects import Block

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
EMBEDDER = HashedTokenEmbedder()


class StubFingerprinter:
    def __init__(self, model_id: str = "stub-model-1") -> None:
        self.model_id = model_id

    def outputs(self, probes):
        from cle.store.objects import content_hash

        return tuple(content_hash({"model": self.model_id, "probe": p}) for p in probes)


def _history() -> list[Message]:
    messages = []
    for week in range(5):
        start = T0 + timedelta(days=7 * week)
        messages.append(
            Message(user_id="u1", ts=start, text="write the weekly recap of my project", thread_id=f"r{week}")
        )
        messages.append(
            Message(user_id="u1", ts=start + timedelta(days=2), text="debug the ingress timeout", thread_id=f"n{week}")
        )
    return messages


def _build(payload: str, store: InMemoryStore | None = None):
    store = store if store is not None else InMemoryStore()
    block = Block(kind="prompt_fragment", payload=payload)
    store.put(block.hash, block.canonical_bytes())
    store.move_ref("blocks/recap_format", block.hash)
    centroid = EMBEDDER.embed("write the weekly recap of my project")
    yaml_raw = (
        "name: weekly_recap\n"
        "components:\n"
        "  - '#blocks/recap_format'\n"
        "trigger:\n"
        "  centroid: [" + ", ".join(str(v) for v in centroid) + "]\n"
    )
    from cle.store.commits import SourceSpec

    return build_image(
        source=SourceSpec(yaml_raw=yaml_raw),
        backend=store,
        messages=_history(),
        window_label="30d",
        existing_triggers=[],
        embedder=EMBEDDER,
        fingerprinter=StubFingerprinter(),
        config=DetectorConfig(),
        oplog=OpLog(io.StringIO()),
        actor="human:test",
    )


@settings(max_examples=15, deadline=None)
@given(payload=st.text(min_size=1, max_size=64))
def test_two_hash_inequality(payload: str) -> None:
    store = InMemoryStore()
    image = _build(payload, store)
    source_hashes = {
        h for h, data in store.snapshot()[0].items() if b'"cle_kind":"source_spec"' in data
    }
    assert image.hash != image.source_hash
    assert image.hash not in source_hashes


@settings(max_examples=15, deadline=None)
@given(payload=st.text(min_size=1, max_size=64))
def test_build_determinism(payload: str) -> None:
    # Same source, same resolved components, same fingerprint => the exact
    # same image hash, across independent stores and runs.
    assert _build(payload).hash == _build(payload).hash


def test_probe_set_is_hash_covered_and_deterministically_selected() -> None:
    # P1 arbitration: probe_set participates in the image identity, and
    # selection is the first PROBE_SET_SIZE in-cluster openers,
    # chronological — no sampling, no wall clock.
    store = InMemoryStore()
    image = _build("recap format v1", store)
    tampered = image.model_copy(update={"probe_set": image.probe_set + ("extra probe",)})
    assert tampered.hash != image.hash
    assert image.probe_set == tuple(
        ["write the weekly recap of my project"] * len(image.probe_set)
    )


def test_image_hash_covers_probe_output_hashes() -> None:
    """Finding 3: mutating probe_output_hashes changes the image hash.

    Both probe_set AND probe_output_hashes participate in the canonical
    encoding (via Storable.canonical_bytes → cle_kind + model_dump), so
    the image address is a commitment to the exact probe outputs frozen
    at build time. The re-validator relies on this: if probe outputs
    could change without moving the image hash, drift detection would be
    comparing against an unstable reference.
    """
    store = InMemoryStore()
    image = _build("recap format v1", store)
    assert len(image.probe_output_hashes) > 0, "image must carry at least one probe output hash"

    # Mutate one probe output hash → image hash must change.
    mutated_hashes = ("0" * 64,) + image.probe_output_hashes[1:]
    tampered = image.model_copy(update={"probe_output_hashes": mutated_hashes})
    assert tampered.hash != image.hash

    # Add an extra probe output hash → image hash must change.
    extended = image.model_copy(
        update={"probe_output_hashes": image.probe_output_hashes + ("extra",)}
    )
    assert extended.hash != image.hash


def test_image_is_stored_and_tag_target_accepts_it() -> None:
    from cle.oplog import OpLog as _OpLog
    from cle.store.commits import assert_tag_target

    store = InMemoryStore()
    image = _build("recap format v1", store)
    assert store.get(image.hash) == image.canonical_bytes()
    assert_tag_target(store, image.hash, _OpLog(io.StringIO()))  # must not raise


def test_successful_build_logs_exactly_one_line_with_pre_evidence() -> None:
    import json

    store = InMemoryStore()
    block = Block(kind="prompt_fragment", payload="recap")
    store.put(block.hash, block.canonical_bytes())
    store.move_ref("blocks/recap_format", block.hash)
    centroid = EMBEDDER.embed("write the weekly recap of my project")
    yaml_raw = (
        "name: weekly_recap\ncomponents:\n  - '#blocks/recap_format'\n"
        "trigger:\n  centroid: [" + ", ".join(str(v) for v in centroid) + "]\n"
    )
    from cle.store.commits import SourceSpec

    sink = io.StringIO()
    build_image(
        source=SourceSpec(yaml_raw=yaml_raw),
        backend=store,
        messages=_history(),
        window_label="30d",
        existing_triggers=[],
        embedder=EMBEDDER,
        fingerprinter=StubFingerprinter(),
        config=DetectorConfig(),
        oplog=OpLog(sink),
        actor="human:test",
    )
    lines = [json.loads(line) for line in sink.getvalue().splitlines()]
    # Two ops, one line each: the closure-mix measurement, then the build.
    assert [line["op"] for line in lines] == ["closure_distribution", "build"]
    assert {"success", "reformulated", "abandoned"} <= set(lines[0])
    record = lines[1]
    assert record["op"] == "build"
    assert record["outcome"] == "succeeded"
    assert record["actor"] == "human:test"
    assert "image" in record
    assert set(record["pre_evidence"]) == {
        "capture_rate",
        "false_trigger_rate",
        "historical_cost",
        "window",
        "semantic_trigger_tested",
        "period_tested",
    }
    assert "latency_ms" in record
