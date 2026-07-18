"""Episode segmentation, silence threshold (decision 1), closure, cold start."""

import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from cle.detect.episodes import (
    DetectorConfig,
    Message,
    classify_closure,
    cold_start_is_over,
    segment,
    silence_threshold,
)
from cle.oplog import OpLog

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
CONFIG = DetectorConfig()


def _messages(*offsets_minutes: float, texts: list[str] | None = None) -> list[Message]:
    return [
        Message(
            user_id="u1",
            ts=T0 + timedelta(minutes=offset),
            text=(texts[i] if texts else f"message {i}"),
        )
        for i, offset in enumerate(offsets_minutes)
    ]


# --- silence threshold (BLUEPRINT §9 decision 1 as settled) ---------------


def test_threshold_sits_on_floor_below_twenty_gaps() -> None:
    # Gaps chosen so 2x median (90 min) EXCEEDS the floor: only the
    # sparse-history clause can explain getting the floor back.
    gaps = [timedelta(minutes=45)] * 19
    assert silence_threshold(gaps, CONFIG) == CONFIG.silence_floor


def test_median_takes_over_at_exactly_twenty_gaps() -> None:
    gaps = [timedelta(minutes=45)] * 20
    assert silence_threshold(gaps, CONFIG) == timedelta(minutes=90)


def test_threshold_is_twice_median_above_floor() -> None:
    gaps = [timedelta(minutes=45)] * 25
    assert silence_threshold(gaps, CONFIG) == timedelta(minutes=90)


def test_threshold_never_drops_below_floor() -> None:
    gaps = [timedelta(minutes=1)] * 50
    assert silence_threshold(gaps, CONFIG) == CONFIG.silence_floor


def test_median_resists_outlier_gaps() -> None:
    # An overnight gap must not drag the threshold up the way a mean would.
    gaps = [timedelta(minutes=10)] * 24 + [timedelta(hours=14)]
    assert silence_threshold(gaps, CONFIG) == CONFIG.silence_floor  # 2*10min < 30min floor


# --- segmentation ----------------------------------------------------------


def test_close_messages_form_one_episode() -> None:
    episodes = segment(_messages(0, 5, 10), CONFIG)
    assert len(episodes) == 1
    assert episodes[0].iterations == 3
    assert episodes[0].opener == "message 0"


def test_silence_splits() -> None:
    # Sparse history -> floor threshold (30 min); a 40-minute gap splits.
    episodes = segment(_messages(0, 5, 45.0 + 5), CONFIG)
    assert [e.iterations for e in episodes] == [2, 1]


def test_marker_matching_respects_word_boundaries() -> None:
    # "thanksgiving" must not close an episode; a stray split would
    # deflate iterations and with it historical_cost.
    episodes = segment(
        _messages(0, 2, 4, texts=["plan thanksgiving dinner", "add a turkey", "thanks"]), CONFIG
    )
    assert len(episodes) == 1
    assert episodes[0].ended_with_marker


def test_success_marker_splits_unconditionally() -> None:
    episodes = segment(
        _messages(0, 2, 4, texts=["do the recap", "thanks!", "new question"]), CONFIG
    )
    assert [e.iterations for e in episodes] == [2, 1]
    assert episodes[0].ended_with_marker
    assert not episodes[1].ended_with_marker


def test_thread_change_splits_unconditionally() -> None:
    messages = [
        Message(user_id="u1", ts=T0, text="a", thread_id="t1"),
        Message(user_id="u1", ts=T0 + timedelta(minutes=1), text="b", thread_id="t1"),
        Message(user_id="u1", ts=T0 + timedelta(minutes=2), text="c", thread_id="t2"),
    ]
    assert [e.iterations for e in segment(messages, CONFIG)] == [2, 1]


def test_segment_requires_single_user_sorted_input() -> None:
    with pytest.raises(ValueError):
        segment(list(reversed(_messages(0, 10))), CONFIG)
    mixed = _messages(0) + [Message(user_id="u2", ts=T0 + timedelta(minutes=1), text="x")]
    with pytest.raises(ValueError):
        segment(mixed, CONFIG)


def test_empty_history_yields_no_episodes() -> None:
    assert segment([], CONFIG) == []


# --- closure (provisional completion of an ambiguous contract cell) --------


def _episode(iterations: int, marker: bool):
    texts = ["q"] * (iterations - 1) + (["thanks"] if marker else ["last"])
    episodes = segment(_messages(*range(0, iterations * 2, 2), texts=texts), CONFIG)
    assert len(episodes) == 1
    return episodes[0]


def test_marker_means_success() -> None:
    episode = _episode(4, marker=True)
    assert classify_closure(episode, returned_to_cluster=False, user_baseline=3.0, config=CONFIG) == "success"
    # Even a return afterwards does not undo an explicit success.
    assert classify_closure(episode, returned_to_cluster=True, user_baseline=3.0, config=CONFIG) == "success"


def test_no_marker_but_return_is_reformulated() -> None:
    episode = _episode(4, marker=False)
    assert (
        classify_closure(episode, returned_to_cluster=True, user_baseline=3.0, config=CONFIG)
        == "reformulated"
    )


def test_silent_cheap_close_is_success() -> None:
    # No marker, no return, cost within 1.5x baseline: satisfied silence.
    episode = _episode(3, marker=False)
    assert (
        classify_closure(episode, returned_to_cluster=False, user_baseline=3.0, config=CONFIG)
        == "success"
    )


def test_silent_expensive_close_is_abandoned() -> None:
    # No marker, no return, cost beyond 1.5x baseline: struggled, then
    # vanished — the anti-Goodhart guard excludes these from baselines.
    episode = _episode(6, marker=False)
    assert (
        classify_closure(episode, returned_to_cluster=False, user_baseline=3.0, config=CONFIG)
        == "abandoned"
    )


# --- cold start ------------------------------------------------------------


def test_short_history_keeps_detector_observing() -> None:
    sink = io.StringIO()
    messages = _messages(0, 5, 10)  # far under 14 days / 20 episodes
    episodes = segment(messages, CONFIG)
    now = T0 + timedelta(days=2)
    assert not cold_start_is_over(messages, episodes, now, CONFIG, OpLog(sink), actor="human:test")
    lines = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert [line["op"] for line in lines] == ["detector_observing"]


def test_cold_start_boundaries_are_inclusive() -> None:
    # Exactly 14 days of history and exactly 20 episodes clears the gate.
    messages = [
        Message(user_id="u1", ts=T0 + timedelta(hours=16 * i), text=f"m{i}", thread_id=f"t{i}")
        for i in range(21)
    ]
    episodes = segment(messages, CONFIG)
    assert len(episodes) == 21
    sink = io.StringIO()
    exactly_14_days = messages[0].ts + timedelta(days=14)
    assert cold_start_is_over(
        messages, episodes[:20], exactly_14_days, CONFIG, OpLog(sink), actor="human:test"
    )
    assert not cold_start_is_over(
        messages, episodes[:19], exactly_14_days, CONFIG, OpLog(sink), actor="human:test"
    )


def test_mature_history_allows_candidates() -> None:
    sink = io.StringIO()
    # 25 episodes spread over 25 days: one thread per day, so thread
    # changes split regardless of the (2-day) silence threshold.
    messages = [
        Message(user_id="u1", ts=T0 + timedelta(days=day), text=f"day {day}", thread_id=f"t{day}")
        for day in range(25)
    ]
    episodes = segment(messages, CONFIG)
    assert len(episodes) == 25
    now = T0 + timedelta(days=25)
    assert cold_start_is_over(messages, episodes, now, CONFIG, OpLog(sink), actor="human:test")
    assert sink.getvalue() == ""
