"""P3: tag ladder, shadow engine, topology chain, revalidator drift."""

import io
import json
from pathlib import Path

import pytest

from cle.lifecycle.engine import EngineThresholds, shadow_decide
from cle.lifecycle.revalidator import revalidate
from cle.lifecycle.tags import TagMoveError, move_state_tag, tag_version
from cle.lifecycle.topology import current_agents, render_diff, render_log, write_topology
from cle.oplog import OpLog
from cle.store.backends import ImmutableRefError, InMemoryStore
from cle.store.commits import Evidence, PreEvidence

from tests.unit.test_runtime import _build_image  # reuse the pipeline helper


def _pre() -> PreEvidence:
    return PreEvidence(
        capture_rate=0.9, false_trigger_rate=0.02, historical_cost=4.0, window="30d"
    )


def _evidence(cost_ratio: float = 0.5, occurrences: int = 4) -> Evidence:
    return Evidence(
        cost_ratio=cost_ratio, occurrences=occurrences, closure_tags=("success",) * occurrences
    )


def _image_in(store, tmp_path):
    return _build_image(store, tmp_path)


# --- tags ------------------------------------------------------------------


def test_tag_ladder_proof_requirements(tmp_path) -> None:
    store = InMemoryStore()
    image = _image_in(store, tmp_path)
    sink = io.StringIO()
    oplog = OpLog(sink)

    # Birth and trial entry ride on pre_evidence.
    move_state_tag(
        backend=store, agent="recap", image_hash=image.hash, from_state=None,
        to_state="candidate", pre_evidence=_pre(), oplog=oplog, actor="human:t",
    )
    move_state_tag(
        backend=store, agent="recap", image_hash=image.hash, from_state="candidate",
        to_state="trial", pre_evidence=_pre(), oplog=oplog, actor="human:t",
    )
    # Promotion without Evidence: refused, even with glowing pre_evidence.
    with pytest.raises(TagMoveError):
        move_state_tag(
            backend=store, agent="recap", image_hash=image.hash, from_state="trial",
            to_state="active", pre_evidence=_pre(), oplog=oplog, actor="human:t",
        )
    move_state_tag(
        backend=store, agent="recap", image_hash=image.hash, from_state="trial",
        to_state="active", evidence=_evidence(), oplog=oplog, actor="human:t",
    )
    # Downward needs a reason.
    with pytest.raises(TagMoveError):
        move_state_tag(
            backend=store, agent="recap", image_hash=image.hash, from_state="active",
            to_state="trial", oplog=oplog, actor="human:t",
        )
    move_state_tag(
        backend=store, agent="recap", image_hash=image.hash, from_state="active",
        to_state="trial", reason="fingerprint drift", oplog=oplog, actor="human:t",
    )
    ops = [json.loads(line) for line in sink.getvalue().splitlines() if '"op": "tag"' in line]
    assert [o.get("to") for o in ops] == ["candidate", "trial", "active", "trial"]
    assert ops[2]["evidence"]["cost_ratio"] == 0.5  # promotion carries evidence


def test_version_tags_are_immutable(tmp_path) -> None:
    store = InMemoryStore()
    image = _image_in(store, tmp_path)
    oplog = OpLog(io.StringIO())
    tag_version(backend=store, agent="recap", semver="1.0.0", image_hash=image.hash, oplog=oplog, actor="human:t")
    with pytest.raises(ImmutableRefError):
        tag_version(backend=store, agent="recap", semver="1.0.0", image_hash=image.hash, oplog=oplog, actor="human:t")


# --- shadow engine ---------------------------------------------------------


def test_shadow_engine_decides_but_never_writes(tmp_path) -> None:
    store = InMemoryStore()
    image = _image_in(store, tmp_path)
    sink = io.StringIO()
    before = store.snapshot()

    would = shadow_decide(
        state="trial", evidence=_evidence(0.5, 4), thresholds=EngineThresholds(),
        image_hash=image.hash, oplog=OpLog(sink),
    )
    assert would == "active"
    assert shadow_decide(
        state="active", evidence=_evidence(1.5, 3), thresholds=EngineThresholds(),
        image_hash=image.hash, oplog=OpLog(sink),
    ) == "trial"
    assert shadow_decide(
        state="trial", evidence=_evidence(1.5, 6), thresholds=EngineThresholds(),
        image_hash=image.hash, oplog=OpLog(sink),
    ) == "archived"
    assert shadow_decide(
        state="trial", evidence=_evidence(0.9, 2), thresholds=EngineThresholds(),
        image_hash=image.hash, oplog=OpLog(sink),
    ) == "hold"

    assert store.snapshot() == before  # shadow means SHADOW
    records = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert all(r["actor"] == "engine:shadow" and "would" in r for r in records)


# --- topology --------------------------------------------------------------


def test_topology_chain_diff_and_log(tmp_path) -> None:
    store = InMemoryStore()
    image = _image_in(store, tmp_path)
    oplog = OpLog(io.StringIO())
    topo = tmp_path / "topology.yaml"

    with pytest.raises(ValueError):  # no proof, no entry
        write_topology(
            backend=store, path=topo, agent="recap", state="trial", image_hash=image.hash,
            cause={}, oplog=oplog, actor="human:t",
        )
    ref1 = write_topology(
        backend=store, path=topo, agent="recap", state="trial", image_hash=image.hash,
        cause={"pre_evidence": _pre().model_dump()}, oplog=oplog, actor="human:t",
    )
    ref2 = write_topology(
        backend=store, path=topo, agent="recap", state="active", image_hash=image.hash,
        cause={"evidence": _evidence().model_dump()}, oplog=oplog, actor="human:t",
    )
    assert (ref1, ref2) == ("topology/v1", "topology/v2")
    assert current_agents(store)["recap"]["state"] == "active"
    assert topo.exists() and "recap" in topo.read_text()
    delta = render_diff(store, "topology/v1", "topology/v2")
    assert "~ recap: trial@" in delta and "-> active@" in delta
    assert "evidence(" in render_log(store)


# --- revalidator -----------------------------------------------------------


class DriftingFingerprinter:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id

    def outputs(self, probes):
        from cle.store.objects import content_hash

        return tuple(content_hash({"model": self.model_id, "probe": p}) for p in probes)


def test_revalidate_holds_then_drifts(tmp_path) -> None:
    store = InMemoryStore()
    image = _image_in(store, tmp_path)  # built with model "stub"
    sink = io.StringIO()

    same = revalidate(
        backend=store, image_hash=image.hash, fingerprinter=DriftingFingerprinter("stub"),
        oplog=OpLog(sink), actor="engine:revalidator",
    )
    assert same.probe_deltas == () and same.fingerprint_now == image.model_fingerprint

    drifted = revalidate(
        backend=store, image_hash=image.hash, fingerprinter=DriftingFingerprinter("new-model"),
        oplog=OpLog(sink), actor="engine:revalidator",
    )
    assert drifted.fingerprint_now != image.model_fingerprint
    assert len(drifted.probe_deltas) == len(image.probe_set) > 0

    ops = [json.loads(line)["op"] for line in sink.getvalue().splitlines()]
    assert ops == ["revalidate", "revalidation_failed"]
