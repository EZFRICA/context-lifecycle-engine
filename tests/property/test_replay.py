"""Replay validation properties: determinism, both rates always computed,
empty-window failure writes nothing (invariant 3).
"""

import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from cle.build.replay import ReplayError, replay_validate
from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.episodes import DetectorConfig, Message
from cle.oplog import OpLog
from cle.store.backends import InMemoryStore
from cle.store.commits import TriggerSpec

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
CONFIG = DetectorConfig()
EMBEDDER = HashedTokenEmbedder()


def _weekly_history() -> list[Message]:
    """Five weekly recap episodes + interleaved unrelated traffic."""
    messages: list[Message] = []
    for week in range(5):
        start = T0 + timedelta(days=7 * week)
        messages.append(
            Message(user_id="u1", ts=start, text="write the weekly recap of my project", thread_id=f"recap{week}")
        )
        messages.append(
            Message(user_id="u1", ts=start + timedelta(minutes=3), text="shorter please thanks", thread_id=f"recap{week}")
        )
        messages.append(
            Message(
                user_id="u1",
                ts=start + timedelta(days=2),
                text="debug the kubernetes ingress timeout",
                thread_id=f"noise{week}",
            )
        )
    return messages


def _trigger() -> TriggerSpec:
    return TriggerSpec(centroid=EMBEDDER.embed("write the weekly recap of my project"))


def _run(messages: list[Message], sink: io.StringIO | None = None):
    return replay_validate(
        trigger=_trigger(),
        messages=messages,
        window_label="30d",
        existing_triggers=[],
        embedder=EMBEDDER,
        config=CONFIG,
        oplog=OpLog(sink if sink is not None else io.StringIO()),
        actor="human:test",
    )


def test_replay_is_deterministic() -> None:
    messages = _weekly_history()
    first, second = _run(messages), _run(messages)
    assert first.pre_evidence == second.pre_evidence
    assert first.in_cluster_openers == second.in_cluster_openers


def test_both_rates_are_always_computed() -> None:
    outcome = _run(_weekly_history())
    # capture over the recap cluster, false triggers over the noise — a
    # capture rate without a false-trigger rate is meaningless.
    assert outcome.pre_evidence.capture_rate == 1.0
    assert outcome.pre_evidence.false_trigger_rate == 0.0
    assert outcome.pre_evidence.historical_cost == 2.0
    assert outcome.pre_evidence.window == "30d"


def test_empty_window_fails_and_writes_nothing() -> None:
    store = InMemoryStore()
    before = store.snapshot()
    sink = io.StringIO()
    with pytest.raises(ReplayError):
        _run([], sink)
    assert store.snapshot() == before
    lines = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert len(lines) == 1
    assert lines[0]["op"] == "build"
    assert lines[0]["stage"] == "replay"
    assert lines[0]["outcome"] == "failed"


def test_out_of_cluster_capture_shows_in_false_trigger_rate() -> None:
    # A promiscuous trigger (centroid on the NOISE topic) must show a
    # nonzero false-trigger rate against recap traffic.
    messages = _weekly_history()
    outcome = replay_validate(
        trigger=TriggerSpec(centroid=EMBEDDER.embed("debug the kubernetes ingress timeout")),
        messages=messages,
        window_label="30d",
        existing_triggers=[],
        embedder=EMBEDDER,
        config=CONFIG,
        oplog=OpLog(io.StringIO()),
        actor="human:test",
    )
    assert outcome.pre_evidence.capture_rate == 1.0  # captures its own cluster
    assert outcome.pre_evidence.false_trigger_rate == 0.0


def test_existing_topology_wins_ties_and_reduces_capture() -> None:
    # If an existing agent already owns the recap intent, the candidate
    # captures nothing — no theft from legitimate routing.
    messages = _weekly_history()
    incumbent = TriggerSpec(centroid=EMBEDDER.embed("write the weekly recap of my project"))
    outcome = replay_validate(
        trigger=_trigger(),
        messages=messages,
        window_label="30d",
        existing_triggers=[incumbent],
        embedder=EMBEDDER,
        config=CONFIG,
        oplog=OpLog(io.StringIO()),
        actor="human:test",
    )
    assert outcome.pre_evidence.capture_rate == 0.0
