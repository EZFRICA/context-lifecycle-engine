"""GDG replay demo — competition, not a clean room.

Why this exists: replaying the events candidate against the raw GDG fixture
prints capture=1.000 / false=0.000 — a tautology. Two biases produce it:

  1. Clean-room build. With no incumbent in `existing_triggers`, a candidate
     trivially captures its whole cluster. Real topologies have incumbents;
     the clean room was the bias. This demo seeds a LEGITIMATE incumbent
     (`venue_booking`, a real prior agent that reserves rooms) that already
     owns part of the scheduling intent, so capture falls below 1.0 honestly.

  2. The events cluster is degenerate: all 45 openers are identical, so no
     single incumbent can own a *fraction* of it (it wins or loses wholesale).
     A realistic fractional number needs a window with genuine phrasing
     variety. This demo therefore builds a constructed window — exactly like
     `prompt_history_adversarial.jsonl` — rather than the raw fixture.

The non-trivial false_trigger is obtained by PLANTING its cause: one
adversarial "bridge" episode (labelled BRIDGE below) that reads out-of-cluster
yet clears the candidate's bar. This is a deliberate construct, documented in
docs/METRICS.md; it engineers the number to show the false-trigger machinery
works, and is not evidence of an emergent false trigger.

Everything here is trigger-only replay (invariant 5): tool_result is decor,
never scored. Run:  .venv/bin/python examples/gdg_demo.py
"""

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cle.build.replay import replay_validate
from cle.detect.clusters import HashedTokenEmbedder, IntentClusterer, cosine
from cle.detect.episodes import DetectorConfig, Message, segment
from cle.detect.stability import analyze_cluster_stability
from cle.oplog import OpLog
from cle.store.commits import TriggerSpec

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
CFG = DetectorConfig()
EMB = HashedTokenEmbedder()
HERE = Path(__file__).resolve().parent

# The events candidate's centroid (what detection would produce) and a
# legitimate incumbent that already reserves rooms — its intent overlaps
# scheduling, so it competes for the reworded "book the room" phrasings.
CANDIDATE_OPENER = "schedule the monthly gdg meetup in the main room"
INCUMBENT_OPENER = "book and reserve the main room booking for the meetup"

# Constructed window openers. CANONICAL episodes are unambiguously the
# candidate's. CONTESTED episodes are reworded toward the incumbent — it
# wins them, so capture < 1.0. SPONSOR is well-separated out-of-cluster
# traffic. BRIDGE is the planted adversarial episode: it reads as sponsor
# work (joins that cluster) yet clears the candidate's bar (a false trigger).
CANONICAL = CANDIDATE_OPENER
CONTESTED = "book the main room booking for the meetup evening"
SPONSOR = "update the sponsor pipeline notes after the call"
BRIDGE = "update the sponsor pipeline notes and schedule the main room"


def _episode_messages(opener: str, thread: str, day: int, tool: str | None, result: str | None):
    ts = T0 + timedelta(days=day)
    return [
        Message(user_id="u", ts=ts, text=opener, thread_id=thread,
                requires_tool=tool, tool_result=result),
        Message(user_id="u", ts=ts + timedelta(minutes=4), text="thanks", thread_id=thread),
    ]


def build_window() -> list[Message]:
    # Order matters for the incremental clusterer: the sponsor cluster is
    # populated FIRST so it holds its own centroid, otherwise events would
    # drift and swallow it (a single-cluster collapse hides out-of-cluster
    # traffic and false_trigger reads a spurious 0).
    msgs: list[Message] = []
    day = 0
    for k in range(6):  # sponsor cluster — the out-of-cluster traffic
        msgs += _episode_messages(SPONSOR, f"spon{k}", day, None, None)
        day += 1
    for k in range(6):  # canonical events — candidate owns these
        msgs += _episode_messages(CANONICAL, f"cand{k}", day, "calendar_api", "slot_free")
        day += 2
    for k in range(4):  # contested rewordings — the incumbent owns these
        msgs += _episode_messages(CONTESTED, f"cont{k}", day, "calendar_api", "no_slot")
        day += 2
    # 1 planted adversarial bridge — joins sponsor, fires on the candidate.
    msgs += _episode_messages(BRIDGE, "bridge0", day, None, None)
    return sorted(msgs, key=lambda m: m.ts)


def main() -> None:
    candidate = TriggerSpec(centroid=EMB.embed(CANDIDATE_OPENER))
    incumbent = TriggerSpec(centroid=EMB.embed(INCUMBENT_OPENER))

    print("=== routing cosines (why competition, not a clean room) ===")
    for label, opener in [("CANONICAL", CANONICAL), ("CONTESTED", CONTESTED),
                          ("SPONSOR", SPONSOR), ("BRIDGE", BRIDGE)]:
        e = EMB.embed(opener)
        print(f"  {label:9} sim(candidate)={cosine(e, candidate.centroid):.3f} "
              f"sim(incumbent)={cosine(e, incumbent.centroid):.3f}")

    messages = build_window()

    print("\n=== clean-room replay (no incumbent) — the tautology ===")
    clean = replay_validate(
        trigger=candidate, messages=messages, window_label="gdg-demo",
        existing_triggers=[], embedder=EMB, config=CFG, oplog=OpLog(io.StringIO()),
        actor="human:demo", mounted_tools=frozenset({"calendar_api"}),
    ).pre_evidence
    print(f"  capture={clean.capture_rate:.3f}  false_trigger={clean.false_trigger_rate:.3f}  "
          f"cost={clean.historical_cost:.2f}")

    print("\n=== competition replay (venue_booking incumbent seeded) ===")
    competed = replay_validate(
        trigger=candidate, messages=messages, window_label="gdg-demo",
        existing_triggers=[incumbent], embedder=EMB, config=CFG, oplog=OpLog(io.StringIO()),
        actor="human:demo", mounted_tools=frozenset({"calendar_api"}),
    ).pre_evidence
    print(f"  capture={competed.capture_rate:.3f}  false_trigger={competed.false_trigger_rate:.3f}  "
          f"cost={competed.historical_cost:.2f}")
    print("  (capture < 1.0: the incumbent owns the reworded 'book the room' episodes;")
    print("   false_trigger > 0: the planted BRIDGE episode — cause deliberately planted.)")

    # Tie back to Action 2: the real events cluster's stability line, with its
    # resolution diagnostic and permanent world_state attribution.
    history = [Message.model_validate(json.loads(line))
               for line in (HERE / "prompt_history_gdg.jsonl").read_text().splitlines() if line.strip()]
    clusterer = IntentClusterer(EMB, CFG)
    clusters: dict[int, list] = {}
    for episode in segment(history, CFG):
        clusters.setdefault(clusterer.assign(episode), []).append(episode)
    events = max(clusters.values(),
                 key=lambda es: sum(1 for e in es if e.required_tool == "calendar_api"))
    print("\n=== real events cluster stability (Action 2 instrumentation) ===")
    sink = io.StringIO()
    report = analyze_cluster_stability(events, EMB, CFG, OpLog(sink), actor="human:demo",
                                       cluster_label="events")
    print(" ", sink.getvalue().strip())
    print(f"  resolution={report.resolution} (all {len(report.pairs)} divergent pairs at one cosine)"
          f" -> unresolvable, not a verdict; world_state absorbs {report.ws_share_pct:.0f}%"
          f" ({report.ws_would_be_intra} would be intra_cluster with an identical tool_result)")


if __name__ == "__main__":
    main()
