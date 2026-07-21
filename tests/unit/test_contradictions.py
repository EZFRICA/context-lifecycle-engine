"""The four-contradiction taxonomy — one focused section per type.

intra_cluster -> unstable, NO candidate. temporal -> evolution, candidate
from the recent segment. routing -> false_trigger_rate. world_state ->
environmental, cluster stays stable, candidate still born. Plus the two
approved adjustments: grey-zone (total partition, unstable by default),
no-tool-never-world_state, and the ADVERSARIAL world_state case (severe
directive flip + tool change -> unstable, not excused).
"""

import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from cle.build.replay import replay_validate
from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.episodes import DetectorConfig, Message, segment
from cle.detect.signals import detect_signal_gated
from cle.detect.stability import analyze_cluster_stability
from cle.oplog import OpLog
from cle.store.commits import TriggerSpec

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
CFG = DetectorConfig()
EMB = HashedTokenEmbedder()


def _episodes(specs):
    """specs: list of (day, opener, directive|None, tool, result)."""
    msgs = []
    for i, (day, opener, directive, tool, result) in enumerate(specs):
        th = f"e{i}"
        ts = T0 + timedelta(days=day)
        msgs.append(Message(user_id="u", ts=ts, text=opener, thread_id=th,
                            requires_tool=tool, tool_result=result))
        if directive:
            msgs.append(Message(user_id="u", ts=ts + timedelta(minutes=3), text=directive, thread_id=th))
        msgs.append(Message(user_id="u", ts=ts + timedelta(minutes=6), text="thanks", thread_id=th))
    return segment(sorted(msgs, key=lambda m: m.ts), CFG)


def _analyze(eps):
    sink = io.StringIO()
    report = analyze_cluster_stability(eps, EMB, CFG, OpLog(sink), actor="human:t", cluster_label="c")
    return report, [json.loads(l) for l in sink.getvalue().splitlines()]


OP = "write the weekly gdg newsletter digest for members"
SHORT = "keep the digest short three bullets maximum no fluff"
LONG = "make the digest long and detailed with full session summaries"


# ── intra_cluster ────────────────────────────────────────────────────────────

def test_intra_cluster_flip_flags_unstable_and_blocks_candidate() -> None:
    eps = _episodes([(d, OP, SHORT if i % 2 == 0 else LONG, None, None)
                     for i, d in enumerate(range(0, 8, 2))])
    report, lines = _analyze(eps)
    assert report.unstable and report.counts["intra_cluster"] >= 1
    assert lines[-1]["op"] == "cluster_stability" and lines[-1]["unstable"] is True
    signal = detect_signal_gated(eps, 3.0, CFG, EMB, OpLog(io.StringIO()), actor="human:t")
    assert signal is None  # don't automate a contradictory cluster


def test_consistent_directives_stay_stable() -> None:
    eps = _episodes([(d, OP, SHORT, None, None) for d in range(0, 8, 2)])
    report, _ = _analyze(eps)
    assert not report.unstable and not any(report.counts.values())


def test_gdg_fixture_newsletter_is_unstable_no_candidate(gdg) -> None:
    _, eps = gdg.cluster_of(OP)
    signal = detect_signal_gated(eps, 3.0, gdg.config, gdg.embedder, gdg.oplog(), actor="human:t")
    assert signal is None


# ── grey zone (adjustment 1: total partition, conservative default) ─────────

def test_grey_zone_gap_is_unstable_by_default() -> None:
    eps = _episodes([(0, OP, SHORT, None, None), (12, OP, LONG, None, None)])  # 7 < 12 < 21
    report, _ = _analyze(eps)
    assert report.counts["grey_zone"] == 1 and report.unstable


@pytest.mark.parametrize("gap,expected", [(3, "intra_cluster"), (12, "grey_zone"), (30, "temporal")])
def test_time_partition_is_total(gap, expected) -> None:
    eps = _episodes([(0, OP, SHORT, None, None), (gap, OP, LONG, None, None)])
    report, _ = _analyze(eps)
    assert report.counts[expected] == 1  # no interval is uncovered


# ── temporal ─────────────────────────────────────────────────────────────────

PLAN = "sort out venue reservations before next month's community event"
OLD = "handle the logistics yourself and book everything directly"
NEW = "always ask me for approval before booking anything"


def test_temporal_evolution_keeps_cluster_stable_recency_wins() -> None:
    eps = _episodes([(d, PLAN, OLD, None, None) for d in (0, 2, 4)]
                    + [(d, PLAN, NEW, None, None) for d in (30, 33, 36, 39)])
    report, _ = _analyze(eps)
    assert not report.unstable and report.counts["temporal"] >= 1
    assert report.stable_from_index == 3  # window starts at the first NEW-regime episode
    signal = detect_signal_gated(eps, 3.0, CFG, EMB, OpLog(io.StringIO()), actor="human:t")
    assert signal is not None  # the recent stable sub-pattern still births


def test_gdg_fixture_venue_policy_births_from_recent(gdg) -> None:
    _, eps = gdg.cluster_of(PLAN)
    signal = detect_signal_gated(eps, 3.0, gdg.config, gdg.embedder, gdg.oplog(), actor="human:t")
    assert signal is not None


# ── routing ──────────────────────────────────────────────────────────────────

M = "prepare the agenda for the gdg meetup night"
W = "draft the workshop agenda for the coding session"
BRIDGE = "prepare the coding workshop agenda for the gdg session"


def test_gdg_routing_pair_stays_two_clusters(gdg) -> None:
    cid_m, _ = gdg.cluster_of(M)
    cid_w, _ = gdg.cluster_of(W)
    assert cid_m != cid_w


def test_routing_bridge_shows_in_false_trigger_rate(gdg) -> None:
    # A bridge mixing both vocabularies clusters w-side yet clears the
    # m-trigger: a genuine cross-cluster steal, surfaced where it belongs.
    msgs = list(gdg.messages)
    ts = msgs[-1].ts + timedelta(hours=1)
    msgs += [Message(user_id="gdg", ts=ts, text=BRIDGE, thread_id="bridge-r"),
             Message(user_id="gdg", ts=ts + timedelta(minutes=3), text="thanks", thread_id="bridge-r")]
    cid_m, _ = gdg.cluster_of(M)
    out = replay_validate(
        trigger=TriggerSpec(centroid=gdg.centroids[cid_m]), messages=msgs, window_label="45d",
        existing_triggers=[], embedder=EMB, config=CFG, oplog=OpLog(io.StringIO()), actor="t",
    )
    assert out.pre_evidence.false_trigger_rate > 0.0
    assert out.pre_evidence.capture_rate == 1.0


# ── world_state (the make-or-break) ─────────────────────────────────────────

EV = "schedule the monthly gdg meetup in the main room"
OK = "great confirm the main room booking and send the invites"
KO = "no room free find an alternative venue for the meetup evening"


def test_world_state_divergence_is_not_a_contradiction() -> None:
    eps = _episodes([(d, EV, OK if i % 2 == 0 else KO, "calendar_api",
                      "slot_free" if i % 2 == 0 else "no_slot")
                     for i, d in enumerate(range(0, 8, 2))])
    report, lines = _analyze(eps)
    assert report.counts["world_state"] >= 1          # divergence attributed to tool_result
    assert report.counts["intra_cluster"] == 0
    assert not report.unstable                        # cluster stays stable
    assert lines[-1]["world_state"] >= 1 and lines[-1]["unstable"] is False
    signal = detect_signal_gated(eps, 3.0, CFG, EMB, OpLog(io.StringIO()), actor="human:t")
    assert signal is not None                         # the candidate is still born


def test_gdg_fixture_events_cluster_stable_and_births(gdg) -> None:
    _, eps = gdg.cluster_of(EV)
    report, _ = _analyze(eps)
    assert not report.unstable and report.counts["world_state"] >= 1
    signal = detect_signal_gated(eps, 3.0, gdg.config, gdg.embedder, gdg.oplog(), actor="human:t")
    assert signal is not None


def test_adversarial_world_state_severe_flip_is_unstable() -> None:
    # Approved adjustment 3: tool_result AND directive both change,
    # incompatibly (severe divergence). A world change must NOT excuse a
    # near-total intent flip — prudence resolves to unstable.
    eps = _episodes([
        (0, EV, "book big hall now every single time", "calendar_api", "slot_free"),
        (3, EV, "quit reserving spaces until my explicit approval arrives", "calendar_api", "no_slot"),
    ])
    report, _ = _analyze(eps)
    assert report.counts["world_state"] == 0
    assert report.counts["intra_cluster"] == 1
    assert report.unstable                             # NOT excluded


def test_no_tool_divergence_is_never_world_state() -> None:
    # Approved adjustment 2: with no external world in the frame (no
    # tool_result on either side), divergence IS a user signal.
    eps = _episodes([(0, OP, SHORT, None, None), (3, OP, LONG, None, None)])
    report, _ = _analyze(eps)
    assert report.counts["world_state"] == 0
    assert report.counts["intra_cluster"] == 1 and report.unstable


def test_one_sided_tool_result_is_not_world_state() -> None:
    # tool_result present on ONE side only: not attributable to a world
    # change — falls through to the time-based classification.
    eps = _episodes([(0, EV, "book big hall now every single time", "calendar_api", "slot_free"),
                     (3, EV, "quit reserving spaces until my explicit approval arrives", "calendar_api", None)])
    report, _ = _analyze(eps)
    assert report.counts["world_state"] == 0 and report.unstable
