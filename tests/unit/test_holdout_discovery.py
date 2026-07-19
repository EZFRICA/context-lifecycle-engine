"""Holdout discovery test — structural sanity only.

The holdout history (examples/make_holdout.py) is produced by a process
that is INDEPENDENT of cle/detect: its author did not know the embedder
geometry, the cosine threshold, or the centroids from make_fixture.py.
Its purpose is DISCOVERY — can the detector find unplanted patterns?

Rules for this test file:
  - Assert STRUCTURAL properties only: ≥1 agent detected, false_trigger_rate
    below a stated ceiling, no crash, log lines well-formed JSON.
  - DO NOT assert exact metric values (capture_rate, false_trigger_rate,
    historical_cost). Asserting exact values would turn the holdout into a
    known fixture and destroy its purpose.  The holdout's job is to surprise;
    let it.
  - DO NOT tune thresholds here to make the numbers look good.  If the
    detector finds nothing, or produces high false-trigger rates, that is
    informative, not a failure mode.

Failure of this test means the DETECTOR IS BROKEN (crash, malformed log,
or nothing detected in 85 days of conversation history).  It does NOT mean
the detector is failing to discover the specific patterns the author intended.
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

def _run_detection(messages: list[Message], config: DetectorConfig):
    """Full detection pipeline; returns (detected_candidates, all_episodes, sink).

    detected_candidates: list of (signal, episodes, centroid) for clusters
    that passed the signal gate.  May be empty — the test will report that.
    """
    sink = io.StringIO()
    oplog = OpLog(sink)

    episodes = segment(messages, config)
    # Cold-start: if the history doesn't clear the gate, there are no candidates
    # and the test should report that but not crash.
    gate_cleared = cold_start_is_over(
        messages, episodes, messages[-1].ts, config, oplog, actor="human:test"
    )

    clusterer = IntentClusterer(HashedTokenEmbedder(), config)
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
      3. At least one agent is detected — the history contains ≥ 3 recurring
         patterns, so total silence would indicate a detector regression.
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

    # ── 3. At least one agent detected ────────────────────────────────────
    # Report what was found (useful for debugging) without asserting exact numbers.
    discovered_names = [signal.kind for signal, _, _ in detected]
    assert len(detected) >= 1, (
        f"expected ≥1 detected agent in the holdout; got 0. "
        f"Episodes: {len(episodes)}, clusters with signals: {discovered_names}. "
        "If the holdout patterns changed, check make_holdout.py."
    )

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

    # ── 6. Replay the strongest discovered candidate: report capture /
    #       false-trigger / historical-cost; assert only the false-trigger
    #       ceiling (the real one, from replay — not a proxy). ─────────────
    strongest_signal, _, strongest_centroid = max(detected, key=lambda d: d[0].occurrences)
    outcome = replay_validate(
        trigger=TriggerSpec(centroid=strongest_centroid),
        messages=messages,
        window_label="holdout",
        existing_triggers=[],
        embedder=HashedTokenEmbedder(),
        config=config,
        oplog=OpLog(io.StringIO()),
        actor="human:test",
    )
    pe = outcome.pre_evidence

    # Reported, never asserted for an exact value — the holdout is allowed to
    # surprise. Only the loose sanity ceiling is a hard gate.
    assert pe.false_trigger_rate <= FALSE_TRIGGER_CEILING, (
        f"holdout false_trigger_rate {pe.false_trigger_rate:.3f} exceeds the loose "
        f"ceiling {FALSE_TRIGGER_CEILING:.2f} — the discovered '{strongest_signal.kind}' "
        f"agent over-fires on unrelated traffic. Report it; do not tune the ceiling."
    )

    # ── Summary (informational, visible with -s) ──────────────────────────
    print(f"\n  holdout: {len(messages)} msgs, {len(episodes)} episodes, "
          f"{len(detected)} agent(s) discovered")
    for signal, eps, centroid in detected:
        print(f"    signal={signal.kind} occ={signal.occurrences} "
              f"episodes={len(eps)} "
              f"period={signal.period.interval if signal.period else None}")
    print(f"  replay(strongest={strongest_signal.kind}): "
          f"capture={pe.capture_rate:.3f} false_trigger={pe.false_trigger_rate:.3f} "
          f"historical_cost={pe.historical_cost:.2f}  (reported, not asserted)")
