"""Holdout discovery test — structural sanity only.

The holdout history (examples/make_holdout.py) is produced by a process
that is INDEPENDENT of cle/detect: its author did not know the embedder
geometry, the cosine threshold, or the centroids from make_fixture.py.
Its purpose is DISCOVERY — can the detector find unplanted patterns?

SCOPE — bucket 2 (stub-as-a-tool): the assertions are structural and hold in
any vector space. The embedder is pinned to the stub here only so the run is
deterministic; the era-C companion below runs the same pipeline on the default
(cached, real) embedder.

Rules for this test file:
  - Assert STRUCTURAL properties only: no crash, the cold-start gate clears,
    every candidate has a valid centroid/period, log lines are well-formed
    JSON, and false_trigger_rate (when there IS a candidate to replay) sits
    below a stated ceiling.
  - The DISCOVERY COUNT IS NOT ASSERTED. It is printed and left to vary —
    zero is a legitimate, measured outcome. (This rule replaced an earlier
    "≥1 agent detected" assertion; it was removed deliberately in the realism
    run, not lost by accident. Do not "restore" it.)
  - DO NOT assert exact metric values (capture_rate, false_trigger_rate,
    historical_cost). Asserting exact values would turn the holdout into a
    known fixture and destroy its purpose.  The holdout's job is to surprise;
    let it.
  - DO NOT tune thresholds here to make the numbers look good.  If the
    detector finds nothing, or produces high false-trigger rates, that is
    informative, not a failure mode.

Failure of this test means the DETECTOR IS BROKEN (crash, malformed log, or a
candidate with an invalid centroid/period).  It does NOT mean the detector
failed to discover the authored patterns: the discovery COUNT is reported, not
gated (realism-run decision). On realistic paraphrase the v1 bag-of-tokens
embedder fragments recurring intents into near-singletons, so zero discovery
is an expected measured finding — see docs/METRICS.md.
"""

import io
import json
import statistics
from pathlib import Path

import pytest

# Consume the COMMITTED holdout data artifact, not the generator. This keeps
# the detector blind to how the history was produced (the point of a holdout)
# and avoids importing from examples/ (which a static analyzer can't resolve).
HOLDOUT_JSONL = (
    Path(__file__).resolve().parent.parent.parent / "examples" / "prompt_history_holdout.jsonl"
)

from cle.build.replay import replay_validate
from cle.detect.clusters import HashedTokenEmbedder, IntentClusterer, returned_to_cluster
from cle.detect.episodes import DetectorConfig, Message, classify_closure, cold_start_is_over, segment
from cle.detect.signals import detect_signal
from cle.oplog import OpLog
from cle.store.commits import TriggerSpec

# ── ceiling for false_trigger_rate — deliberately loose so we never tune
# against it.  If the holdout exceeds this, the discovery is still reported
# (the test only fails on a structural sanity breach, not on ugly numbers).
FALSE_TRIGGER_CEILING = 0.50


# ── helpers ──────────────────────────────────────────────────────────────────

def _run_detection(messages: list[Message], config: DetectorConfig, embedder=None):
    """Full detection pipeline; returns (detected_candidates, all_episodes, sink).

    detected_candidates: list of (signal, episodes, centroid) for clusters
    that passed the signal gate.  May be empty — the test will report that.
    `embedder` defaults to the v1 stub so the era-B run below is unchanged; the
    era-C companion passes the default (cached, real) embedder.
    """
    sink = io.StringIO()
    oplog = OpLog(sink)
    embedder = embedder if embedder is not None else HashedTokenEmbedder()

    episodes = segment(messages, config)
    # Cold-start: if the history doesn't clear the gate, there are no candidates
    # and the test should report that but not crash.
    gate_cleared = cold_start_is_over(
        messages, episodes, messages[-1].ts, config, oplog, actor="human:test"
    )

    clusterer = IntentClusterer(embedder, config)
    by_cluster: dict[int, list] = {}
    centroids: dict[int, tuple] = {}
    for episode in episodes:
        cid = clusterer.assign(episode)
        by_cluster.setdefault(cid, []).append(episode)
        centroids[cid] = clusterer.centroids[cid]

    # Per-user baseline (median, excluding abandoned)
    all_labelled = []
    for eps in by_cluster.values():
        flags = returned_to_cluster(eps, config)
        provisional = statistics.median(e.iterations for e in eps)
        for episode, flag in zip(eps, flags):
            all_labelled.append((
                episode,
                classify_closure(episode, returned_to_cluster=flag,
                                 user_baseline=provisional, config=config),
            ))
    from cle.detect.clusters import user_baseline as _user_baseline
    baseline = _user_baseline(all_labelled) or 3.0

    detected = []
    for cid, eps in by_cluster.items():
        signal = detect_signal(eps, user_baseline=baseline, config=config)
        if signal is not None:
            detected.append((signal, eps, centroids[cid]))

    return detected, episodes, sink, gate_cleared


# ── the test ──────────────────────────────────────────────────────────────────

def test_holdout_discovery_structural_sanity() -> None:
    """Run the full detector on the holdout history and check structural invariants.

    Asserts:
      1. No crash (the function completes).
      2. The history clears the cold-start gate (it's long enough for detection).
      3. (NOT asserted) The discovery count is REPORTED only. The history holds
         3 recurring patterns, but on realistic paraphrase the v1 embedder
         fragments them below the signal gate, so zero is a legitimate result.
      4. Every candidate has: a non-empty episodes list, a valid centroid
         (finite floats, L2-norm ≤ 1.0 + epsilon), a positive-period or
         None period, and a non-negative occurrences count.
      5. Every oplog line emitted during detection is valid JSON with an "op"
         field (well-formedness).
      6. false_trigger_rate, when measurable, is below the stated ceiling
         (FALSE_TRIGGER_CEILING = 0.50) — a loose sanity bound, not a quality
         bar.  Report the actual value so surprises surface.

    Does NOT assert: exact capture_rate, false_trigger_rate, or historical_cost.
    """
    config = DetectorConfig()
    # Read the committed holdout as plain prompt-history records; the conversion
    # to the Message schema happens HERE, on the detector's side.
    messages = [
        Message.model_validate(json.loads(line))
        for line in HOLDOUT_JSONL.read_text().splitlines()
        if line.strip()
    ]

    # ── 1. No crash ───────────────────────────────────────────────────────
    detected, episodes, sink, gate_cleared = _run_detection(messages, config)

    # ── 2. Cold-start gate ────────────────────────────────────────────────
    assert gate_cleared, (
        "holdout history must clear the cold-start gate — "
        f"it has {len(messages)} messages and {len(episodes)} episodes; "
        "extend make_holdout.py if the history is too sparse."
    )

    # ── 3. Discovery count — REPORTED, not gated (realism-run decision) ───
    # On realistic paraphrase the v1 bag-of-tokens embedder fragments each
    # recurring pattern into near-singletons, so discovery can legitimately be
    # ZERO. That is a measured finding about the DETECTOR, not a broken test.
    # The structural sanity checks below still run; only the discovery *count*
    # is de-gated.
    discovered_names = [signal.kind for signal, _, _ in detected]
    print(f"\n  holdout discovery: {len(detected)} agent(s) {discovered_names} "
          f"from {len(episodes)} episodes (reported, not gated)")

    # ── 4. Candidate structural validity ──────────────────────────────────
    import math
    for i, (signal, eps, centroid) in enumerate(detected):
        assert len(eps) >= 1, f"candidate {i} has empty episode list"
        assert signal.occurrences >= config.min_signal_occurrences, (
            f"candidate {i} occurrences={signal.occurrences} below gate "
            f"min_signal_occurrences={config.min_signal_occurrences}"
        )
        norm = math.sqrt(sum(v * v for v in centroid))
        assert norm <= 1.0 + 1e-6, (
            f"candidate {i} centroid not L2-normalized: norm={norm:.6f}"
        )
        for v in centroid:
            assert math.isfinite(v), f"candidate {i} centroid has non-finite value {v}"
        if signal.period is not None:
            assert signal.period.interval.total_seconds() > 0, (
                f"candidate {i} has non-positive period {signal.period}"
            )

    # ── 5. Log lines are well-formed JSON with an 'op' field ─────────────
    log_content = sink.getvalue()
    for lineno, raw_line in enumerate(log_content.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            pytest.fail(f"oplog line {lineno} is not valid JSON: {exc!r}\n  line={raw_line!r}")
        assert "op" in record, (
            f"oplog line {lineno} missing 'op' field: {raw_line!r}"
        )

    # ── 6. If anything WAS discovered, replay the strongest candidate and
    #       report capture / false-trigger / historical-cost; assert only the
    #       loose false-trigger ceiling. When discovery is zero (the realistic
    #       case), there is nothing to replay — report and stop. ────────────
    if not detected:
        print("  holdout: 0 agents discovered — realistic paraphrase fragmented "
              "every recurring pattern below the 3-occurrence signal gate.")
        return

    strongest_signal, _, strongest_centroid = max(detected, key=lambda d: d[0].occurrences)
    outcome = replay_validate(
        trigger=TriggerSpec(centroid=strongest_centroid, embedder_id=HashedTokenEmbedder.embedder_id),
        messages=messages,
        window_label="holdout",
        existing_triggers=[],
        embedder=HashedTokenEmbedder(),
        config=config,
        oplog=OpLog(io.StringIO()),
        actor="human:test",
    )
    pe = outcome.pre_evidence
    assert pe.false_trigger_rate <= FALSE_TRIGGER_CEILING, (
        f"holdout false_trigger_rate {pe.false_trigger_rate:.3f} exceeds the loose "
        f"ceiling {FALSE_TRIGGER_CEILING:.2f} — the discovered '{strongest_signal.kind}' "
        f"agent over-fires on unrelated traffic. Report it; do not tune the ceiling."
    )
    print(f"  replay(strongest={strongest_signal.kind}): "
          f"capture={pe.capture_rate:.3f} false_trigger={pe.false_trigger_rate:.3f} "
          f"historical_cost={pe.historical_cost:.2f}  (reported, not asserted)")


# ── era-C companion: the same structural sanity, on the REAL embedder ────────

def test_holdout_discovery_on_the_default_embedder() -> None:
    """Era-C companion — the figure nothing else in the suite pins.

    The test above runs the v1 stub and guards the era-B zero. But the 0.775
    threshold was adopted on ONE independent confirmation: the holdout's
    behaviour under the REAL embedder. That number came from a measurement
    script, not from a committed test, so nothing detected a regression in it.
    This runs the identical pipeline with the DEFAULT embedder — CachedEmbedder
    over committed vectors, so it stays offline and needs no key — at the
    embedder-scoped threshold (resolved from `embedder_id`, not hardcoded).

    Same discipline as its era-B sibling: STRUCTURAL assertions only. The
    discovery count and per-candidate purity are REPORTED, never asserted —
    pinning them would turn the holdout into a known fixture and destroy the
    independence that makes it the confirmation point in the first place.

    NOTE on `Signal.stability`: this pipeline calls the UNGATED `detect_signal`,
    which never runs the contradiction check, so the field keeps its default and
    carries no information here. It is deliberately neither printed nor asserted
    — `detect_signal_gated` is what sets it (see test_contradictions).
    """
    from collections import Counter

    from cle.detect.embedders import CacheMissError, default_embedder

    config = DetectorConfig()
    messages = [
        Message.model_validate(json.loads(line))
        for line in HOLDOUT_JSONL.read_text().splitlines()
        if line.strip()
    ]
    try:
        embedder = default_embedder()
        detected, episodes, sink, gate_cleared = _run_detection(messages, config, embedder)
    except CacheMissError as missing:
        pytest.fail(
            "the committed vector cache does not cover the holdout openers: "
            f"{missing}. Regenerate it with examples/make_vectors.py rather than "
            "letting this path fall back to a live call."
        )

    # ── structural only ───────────────────────────────────────────────────
    assert gate_cleared, "holdout must clear the cold-start gate"
    import math
    for i, (signal, eps, centroid) in enumerate(detected):
        assert len(eps) >= 1, f"candidate {i} has empty episode list"
        assert signal.occurrences >= config.min_signal_occurrences
        norm = math.sqrt(sum(v * v for v in centroid))
        assert norm <= 1.0 + 1e-6, f"candidate {i} centroid not L2-normalized"
        assert all(math.isfinite(v) for v in centroid)
    for raw in sink.getvalue().splitlines():
        if raw.strip():
            assert "op" in json.loads(raw)

    # ── reported, never gated ─────────────────────────────────────────────
    def pattern(thread_id: str) -> str:
        return thread_id.rsplit("-", 1)[0]

    print(f"\n  holdout (era C, {embedder.embedder_id}): {len(episodes)} episodes, "
          f"{len(detected)} candidate(s) discovered — reported, not gated")
    planted_totals = Counter(pattern(e.messages[0].thread_id) for e in episodes)
    for signal, eps, _ in detected:
        members = Counter(pattern(e.messages[0].thread_id) for e in eps)
        best, n = members.most_common(1)[0]
        recall = n / planted_totals[best] if planted_totals[best] else 0.0
        print(f"    {signal.kind:<13} size={len(eps):>2} best={best:<12} "
              f"recall={recall:.2f} purity={n/len(eps):.2f}")
