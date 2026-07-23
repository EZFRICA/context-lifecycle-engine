"""Replay-time capability gating: capture = centroid match AND tool mount.

tool_result is decor: read, never asserted correct (invariant 5).
"""

import io
from datetime import datetime, timedelta, timezone

import pytest

from cle.build.replay import replay_validate
from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.episodes import DetectorConfig, Message
from cle.oplog import OpLog
from cle.store.commits import TriggerSpec

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
CFG = DetectorConfig()
EMB = HashedTokenEmbedder()
OPENER = "schedule the monthly gdg meetup in the main room"
NOISE = "explain the difference between tokio tasks and threads"


def _history(requires: str | None, results: list[str | None]) -> list[Message]:
    msgs = []
    for i, res in enumerate(results):
        th = f"e{i}"
        start = T0 + timedelta(days=3 * i)
        msgs.append(Message(user_id="u1", ts=start, text=OPENER, thread_id=th,
                            requires_tool=requires, tool_result=res))
        msgs.append(Message(user_id="u1", ts=start + timedelta(minutes=4), text="thanks", thread_id=th))
        msgs.append(Message(user_id="u1", ts=start + timedelta(hours=5), text=NOISE, thread_id=f"n{i}"))
        msgs.append(Message(user_id="u1", ts=start + timedelta(hours=5, minutes=4), text="thanks", thread_id=f"n{i}"))
    return sorted(msgs, key=lambda m: m.ts)


def _replay(messages, mounted: frozenset[str]):
    return replay_validate(
        trigger=TriggerSpec(centroid=EMB.embed(OPENER), embedder_id=EMB.embedder_id), messages=messages,
        window_label="t", existing_triggers=[], embedder=EMB, config=CFG,
        oplog=OpLog(io.StringIO()), actor="human:t", mounted_tools=mounted,
    )


def test_capture_requires_centroid_and_mount() -> None:
    messages = _history("calendar_api", ["slot_free"] * 4)
    with_tool = _replay(messages, frozenset({"calendar_api"}))
    without = _replay(messages, frozenset())
    assert with_tool.pre_evidence.capture_rate == 1.0
    # Same centroid match, missing capability: episodes stay in the
    # denominator and are NOT captured — the gap is visible, not hidden.
    assert without.pre_evidence.capture_rate == 0.0


def test_toolless_episodes_unaffected_by_mount_set() -> None:
    messages = _history(None, [None] * 4)
    assert _replay(messages, frozenset()).pre_evidence.capture_rate == 1.0
    assert _replay(messages, frozenset({"calendar_api"})).pre_evidence.capture_rate == 1.0


def test_partial_capability_gives_partial_capture() -> None:
    # 2 episodes need the tool, 2 don't (mixed cluster): capture = 0.5
    # without the mount.
    msgs = []
    for i in range(4):
        th = f"e{i}"; start = T0 + timedelta(days=3 * i)
        msgs.append(Message(user_id="u1", ts=start, text=OPENER, thread_id=th,
                            requires_tool="calendar_api" if i < 2 else None))
        msgs.append(Message(user_id="u1", ts=start + timedelta(minutes=4), text="thanks", thread_id=th))
        msgs.append(Message(user_id="u1", ts=start + timedelta(hours=5), text=NOISE, thread_id=f"n{i}"))
        msgs.append(Message(user_id="u1", ts=start + timedelta(hours=5, minutes=4), text="thanks", thread_id=f"n{i}"))
    out = _replay(sorted(msgs, key=lambda m: m.ts), frozenset())
    assert out.pre_evidence.capture_rate == pytest.approx(0.5)


def test_capability_gating_is_deterministic() -> None:
    messages = _history("calendar_api", ["no_slot", "slot_free", "no_slot", "slot_free"])
    a = _replay(messages, frozenset({"calendar_api"}))
    b = _replay(messages, frozenset({"calendar_api"}))
    assert a.pre_evidence == b.pre_evidence


def test_tool_result_is_decor_not_verdict() -> None:
    # Two windows identical except for tool_result values: replay numbers
    # are identical — no code path scores the result as right or wrong.
    a = _replay(_history("calendar_api", ["slot_free"] * 4), frozenset({"calendar_api"}))
    b = _replay(_history("calendar_api", ["no_slot"] * 4), frozenset({"calendar_api"}))
    assert a.pre_evidence == b.pre_evidence
