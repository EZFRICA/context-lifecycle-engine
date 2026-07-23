"""Anti-templating guard on the committed fixtures.

The point: a fixture that regresses to templated text (identical openers, two
follow-ups, one closer, fixed timing) must become a TEST FAILURE here, not a
discovery three runs later. All assertions are DATA properties, grouped by the
PLANTED intent (from the sidecar / thread prefix), never by DETECTED clusters
— whether the v1 embedder recovers those intents is a measured finding
(docs/METRICS.md), deliberately not gated here (see the realism run decision).
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from cle.detect.clusters import HashedTokenEmbedder, cosine
from cle.detect.episodes import DetectorConfig, Message, segment
from cle.detect.stability import _directive_text

EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"
CFG = DetectorConfig()
EMB = HashedTokenEmbedder()


def _load(name: str) -> list[Message]:
    return [Message.model_validate(json.loads(line))
            for line in (EXAMPLES / name).read_text().splitlines() if line.strip()]


def _planted_intent(thread_id: str) -> str:
    # Threads are "<intent>-<...>"; the intent is everything before the first
    # hyphen ("agenda_meetup-3" -> "agenda_meetup", "events-1-0" -> "events").
    return thread_id.split("-", 1)[0]


def _episodes_by_intent(messages: list[Message]) -> dict[str, list]:
    by: dict[str, list] = {}
    for e in segment(messages, CFG):
        by.setdefault(_planted_intent(e.messages[0].thread_id), []).append(e)
    return by


# ── the GDG ground-truth fixture ────────────────────────────────────────────

GDG = "prompt_history_gdg.jsonl"


def _gdg_planted() -> list[str]:
    ground = json.loads((EXAMPLES / "gdg_ground_truth.json").read_text())
    return ground["planted_intents"]


@pytest.mark.parametrize("intent", _gdg_planted())
def test_each_planted_intent_has_eight_plus_distinct_openers(intent) -> None:
    by = _episodes_by_intent(_load(GDG))
    openers = {e.opener for e in by[intent]}
    assert len(openers) >= 8, f"{intent}: only {len(openers)} distinct openers (templated?)"


def test_no_single_sentence_dominates_gdg() -> None:
    msgs = _load(GDG)
    freq = Counter(m.text for m in msgs)
    text, n = freq.most_common(1)[0]
    assert n / len(msgs) <= 0.15, f"{text!r} is {100*n/len(msgs):.1f}% of messages (templated closer?)"


def test_gdg_timing_is_not_single_valued() -> None:
    msgs = _load(GDG)
    hours = {m.ts.hour for m in msgs}
    assert len(hours) >= 5, f"only {len(hours)} distinct hours-of-day"
    by_thread: dict[str, list[datetime]] = {}
    for m in msgs:
        by_thread.setdefault(m.thread_id, []).append(m.ts)
    gaps = {round((b - a).total_seconds() / 60)
            for ts in by_thread.values() for a, b in zip(sorted(ts), sorted(ts)[1:])}
    assert len(gaps) >= 5, f"only {len(gaps)} distinct within-thread turn-gaps"


def test_tool_bearing_intent_directive_band_is_not_degenerate() -> None:
    # The events intent is tool-bearing; its divergent-pair directive cosines
    # must SPREAD (band_width > the degeneracy floor). A degenerate band means
    # the follow-ups were templated — the exact defect that made moderate-band
    # calibration impossible in the old fixture.
    by = _episodes_by_intent(_load(GDG))
    events = sorted(by["events"], key=lambda e: e.started_at)
    dirs = [EMB.embed(_directive_text(e)) for e in events]
    cosines = [cosine(dirs[i], dirs[j])
               for i in range(len(dirs)) for j in range(i + 1, len(dirs))
               if cosine(dirs[i], dirs[j]) < CFG.directive_divergence_threshold]
    assert cosines, "no divergent pairs at all — follow-ups collapsed to one point"
    band = max(cosines) - min(cosines)
    assert band > CFG.degenerate_band_width, f"events directive band {band:.4f} is degenerate"


# ── the holdout (discovery) fixture ─────────────────────────────────────────

HOLDOUT = "prompt_history_holdout.jsonl"


def _holdout_intent(thread_id: str) -> str:
    # "meetup-prep-3" -> "meetup-prep"; "outreach-2" -> "outreach".
    return thread_id.rsplit("-", 1)[0]


@pytest.mark.parametrize("intent", ["meetup-prep", "outreach", "venue"])
def test_holdout_recurring_pattern_has_eight_plus_distinct_openers(intent) -> None:
    by: dict[str, list] = {}
    for e in segment(_load(HOLDOUT), CFG):
        by.setdefault(_holdout_intent(e.messages[0].thread_id), []).append(e)
    openers = {e.opener for e in by[intent]}
    assert len(openers) >= 8, f"{intent}: only {len(openers)} distinct openers (templated?)"


def test_no_single_sentence_dominates_holdout() -> None:
    msgs = _load(HOLDOUT)
    text, n = Counter(m.text for m in msgs).most_common(1)[0]
    assert n / len(msgs) <= 0.15, f"{text!r} is {100*n/len(msgs):.1f}% of holdout messages"
