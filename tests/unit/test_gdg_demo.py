"""The GDG demo must show competition, not a clean-room tautology.

Locks the two numbers the demo publishes: a legitimate incumbent drops
capture below 1.0, and the planted bridge yields a non-trivial false_trigger.
Both are trigger-only replay (invariant 5); tool_result is never scored.
"""

import io

from cle.build.replay import replay_validate
from cle.oplog import OpLog
from cle.store.commits import TriggerSpec

import gdg_demo as demo


def _replay(existing):
    return replay_validate(
        trigger=TriggerSpec(centroid=demo.EMB.embed(demo.CANDIDATE_OPENER), embedder_id=demo.EMB.embedder_id),
        messages=demo.build_window(), window_label="t", existing_triggers=existing,
        embedder=demo.EMB, config=demo.CFG, oplog=OpLog(io.StringIO()),
        actor="human:test", mounted_tools=frozenset({"calendar_api"}),
    ).pre_evidence


def test_incumbent_competition_drops_capture_below_one() -> None:
    incumbent = TriggerSpec(centroid=demo.EMB.embed(demo.INCUMBENT_OPENER), embedder_id=demo.EMB.embedder_id)
    clean = _replay([])
    competed = _replay([incumbent])
    assert clean.capture_rate == 1.0            # clean room is the tautology
    assert competed.capture_rate < 1.0          # the incumbent owns the contested episodes
    assert competed.capture_rate == 0.6


def test_planted_bridge_gives_non_trivial_false_trigger() -> None:
    # The bridge is a deliberate adversarial construct (documented in
    # docs/METRICS.md): it exists to prove the false-trigger machinery fires.
    both = _replay([TriggerSpec(centroid=demo.EMB.embed(demo.INCUMBENT_OPENER), embedder_id=demo.EMB.embedder_id)])
    assert 0.0 < both.false_trigger_rate < 1.0
