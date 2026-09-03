"""Build-stage guards, and two that cannot fire.

`python tools/mutate.py` decides by experiment which guards a suite enforces.
These are the build-stage ones it reaches.

Two of them are the difference between a measurement and an invented number:

  * the fingerprinter's live-probe failure. Under `CLE_FORCE_REAL_MODEL=1` a
    failed call must raise, because the offline fallback hashes the probe TEXT:
    plausible, deterministic, and unrelated to any model. A build would report a
    fingerprint and a later revalidation would compare against it, so a network
    outage would read as substrate stability.
  * the all-abandoned cost baseline. Abandoned episodes are excluded from cost
    baselines, so if every in-cluster episode was abandoned there is no baseline
    and `historical_cost` must not be invented.

The others pin staged failure: resolve, replay and assemble fail having written
nothing.

The last two tests are a different shape. They pin why two guards in
`replay.py` are UNREACHABLE, and go red if the surrounding logic changes to make
them reachable.

SCOPE: bucket 1 (embedder-agnostic) except where a stub embedder is used as a
tool; no assertion here depends on a vector space.
"""

from __future__ import annotations

import io
import json

import pytest

from cle.build.assembler import AssemblyError, assemble, parse_trigger
from cle.build.replay import ReplayError, replay_validate
from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.episodes import DetectorConfig, Message
from cle.oplog import OpLog
from cle.store.backends import InMemoryStore
from cle.store.commits import SourceSpec
from cle.store.objects import _canonical_json_bytes, content_hash


def _spec(yaml_text: str) -> SourceSpec:
    return SourceSpec(yaml_raw=yaml_text)


# ── assembler.py:76 — a source with no centroid ────────────────────────────

def test_a_source_without_a_trigger_centroid_is_refused() -> None:
    """The detector writes the centroid; a hand-written spec may forget it.

    Assembling anyway would produce an Image whose `TriggerSpec` has no
    centroid, so routing would compare against nothing and `capture_rate` would
    be computed over an empty cluster. The failure has to happen here, before
    anything is hashed into the store.
    """
    with pytest.raises(AssemblyError, match="trigger.centroid"):
        parse_trigger(_spec("name: recap\ncomponents: []\n"))


@pytest.mark.parametrize("trigger", [
    "trigger: {}",                                  # no centroid key
    "trigger: {centroid: 0.5}",                     # scalar, not a list
    "trigger: null",                                # explicitly absent
])
def test_a_malformed_trigger_is_refused_whatever_shape_it_takes(trigger: str) -> None:
    # One test per shape, because the guard is an `isinstance` pair and a
    # single example would leave half of it free.
    with pytest.raises(AssemblyError):
        parse_trigger(_spec(f"name: recap\n{trigger}\n"))


def test_a_well_formed_trigger_still_parses() -> None:
    # The negative. A guard that refused everything would satisfy the three
    # tests above on its own.
    trigger = parse_trigger(_spec(
        "name: recap\ntrigger:\n  centroid: [1.0, 0.0]\n"
        "  embedder_id: stub:hashed64\n"
    ))
    assert trigger.centroid == (1.0, 0.0)
    assert trigger.embedder_id == "stub:hashed64"


# ── assembler.py:117 — a component ref that is not a block ─────────────────

def test_a_component_ref_pointing_at_a_non_block_is_refused() -> None:
    """The store is content-addressed, not typed: any hash resolves.

    A ref that happens to point at a topology record, or at an image, would
    otherwise be concatenated into `assembled_prompt` as if it were prompt
    text. The image would hash cleanly and carry someone else's record inside.
    """
    from cle.build.assembler import assemble
    from cle.build.replay import ReplayOutcome
    from cle.store.commits import PreEvidence, TriggerSpec

    store = InMemoryStore()
    oplog = OpLog(io.StringIO())

    record = {"cle_kind": "topology", "version": 1, "agents": {}}
    digest = content_hash(record)
    store.put(digest, _canonical_json_bytes(record))

    with pytest.raises(AssemblyError, match="not a block"):
        assemble(
            source=_spec("name: recap\n"),
            resolved_refs={"#components/impostor": digest},
            trigger=TriggerSpec(centroid=(1.0, 0.0), embedder_id="stub:hashed64"),
            replay_outcome=ReplayOutcome(
                pre_evidence=PreEvidence(
                    capture_rate=1.0, false_trigger_rate=0.0,
                    historical_cost=2.0, window="30d",
                ),
                in_cluster_openers=("write the weekly recap",),
                closure_counts={"success": 1},
            ),
            backend=store, fingerprinter=_StubFingerprinter(), oplog=oplog,
        )


class _StubFingerprinter:
    def outputs(self, probes):
        return tuple(content_hash({"probe": p}) for p in probes)


# ── fingerprinter.py:75 — a failed probe must not become a fingerprint ─────
def test_a_failed_probe_under_force_real_model_raises_instead_of_faking() -> None:
    """The guard that separates a measurement from an invented number.

    With `CLE_FORCE_REAL_MODEL=1` the caller has said "I want the live model".
    If the call then fails, the offline fallback hashes the PROBE TEXT, which
    is deterministic, plausible, and completely unrelated to any model. A build
    would report a fingerprint and a revalidation would later compare against
    it, so a network outage would read as substrate stability.
    """
    from cle.build import fingerprinter as module

    class _Failing:
        def invoke(self, prompt):
            raise ConnectionError("no route to host")

    live = object.__new__(module.LiveModelFingerprinter)
    live.model = _Failing()

    import os
    os.environ["CLE_FORCE_REAL_MODEL"] = "1"
    try:
        with pytest.raises(RuntimeError, match="CLE_FORCE_REAL_MODEL"):
            live.outputs(("what is 2+2?",))
    finally:
        os.environ.pop("CLE_FORCE_REAL_MODEL", None)


def test_without_the_flag_a_failed_probe_falls_back_deterministically() -> None:
    """The documented offline behaviour, pinned so the fix above cannot overreach.

    Removing the fallback would break every CI run. The fallback hashes the
    probe, so a failed call reads as "no signal", never as drift: two failed
    runs produce the same hash and the re-validator sees no change.
    """
    from cle.build import fingerprinter as module

    class _Failing:
        def invoke(self, prompt):
            raise ConnectionError("no route to host")

    live = object.__new__(module.LiveModelFingerprinter)
    live.model = _Failing()

    import os
    os.environ.pop("CLE_FORCE_REAL_MODEL", None)
    first = live.outputs(("what is 2+2?",))
    second = live.outputs(("what is 2+2?",))
    assert first == second, "a failed probe must read as no signal, never as drift"


# ── replay.py:172 and :222 — UNREACHABLE, and that is the finding ──────────

def test_the_no_in_cluster_guard_cannot_fire_and_this_pins_why() -> None:
    """The "no in-cluster episodes" guard is structurally unreachable.

    It is not untested but untestable: no input exists that reaches it. The
    proof is two lines of the surrounding code:

      * `IntentClusterer.assign` never returns None. When nothing is close
        enough it FOUNDS a cluster and returns its id, so every episode in the
        window belongs to some cluster.
      * `target_cluster` is `max(range(len(centroids)), key=...)`, and every
        centroid in that range was founded by an episode of this window.

    So `in_cluster` contains at least the episode that founded the chosen
    cluster, always. The empty case is already covered upstream at `:154`
    ("replay window contains no episodes").

    THIS TEST GOES RED IF THAT CHANGES. If `assign` gains a None return (a real
    option: a minimum-similarity floor would want one), the guard becomes
    reachable and needs a behavioural test instead of this one.
    """
    from cle.detect.clusters import IntentClusterer
    import inspect

    source = inspect.getsource(IntentClusterer.assign_opener)
    assert "return len(self.centroids) - 1" in source, (
        "assign_opener no longer founds a cluster unconditionally; the "
        "no-in-cluster guard may now be reachable and needs a behavioural test"
    )
    assert "return None" not in source

    clusterer = IntentClusterer(HashedTokenEmbedder(), DetectorConfig())
    ids = [clusterer.assign_opener(text) for text in
           ("deploy the staging cluster", "write the weekly recap", "book a room")]
    assert all(isinstance(i, int) for i in ids)
    assert set(ids) == set(range(len(clusterer.centroids))), (
        "every cluster id in range was founded by an opener in this window, so "
        "the max() below can never select an empty cluster"
    )


def test_the_all_abandoned_guard_cannot_fire_and_this_pins_why() -> None:
    """The "all abandoned" guard is unreachable for an arithmetic reason.

    An episode is `abandoned` only when its iterations exceed
    `reformulation_cost_multiplier * user_baseline`, and the baseline used here
    is the MEDIAN of the very episodes being classified. At least half of any
    set sits at or below its own median, and 1.5 x median is above the median,
    so at least half classify as `success`. `countable` is never empty.

    The comment above the guard is therefore describing a case that cannot
    arise. It is the documentation that should change, not the code: deleting
    the guard would be right today and wrong the day the baseline stops being
    an internal median (using yesterday's baseline, as the docstring of
    `classify_closure` says the design intends, would make it reachable at once).

    THIS TEST GOES RED IF THE BASELINE STOPS BEING THE INTERNAL MEDIAN.
    """
    import inspect
    import statistics

    from cle.build import replay as module

    source = inspect.getsource(module._replay)
    assert "statistics.median(e.iterations for e in in_cluster)" in source, (
        "the provisional baseline is no longer the median of in_cluster; the "
        "all-abandoned guard may now be reachable and needs a behavioural test"
    )

    for iterations in ([1, 1, 1], [1, 2, 3], [1, 1, 50], [4, 9, 9, 100]):
        baseline = float(statistics.median(iterations))
        countable = [n for n in iterations
                     if not n > DetectorConfig().reformulation_cost_multiplier * baseline]
        assert countable, (
            f"{iterations} produced an empty cost baseline, so the guard IS "
            "reachable and this test is the wrong shape"
        )
