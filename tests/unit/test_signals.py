"""Baselines, return-to-cluster, and reformulation/recurrence signals."""

from datetime import datetime, timedelta, timezone

from cle.detect.clusters import returned_to_cluster, user_baseline
from cle.detect.episodes import DetectorConfig, Episode, Message
from cle.detect.signals import detect_signal

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
CONFIG = DetectorConfig()


def _episode(start: datetime, iterations: int) -> Episode:
    return Episode(
        user_id="u1",
        messages=tuple(
            Message(user_id="u1", ts=start + timedelta(minutes=2 * i), text=f"m{i}")
            for i in range(iterations)
        ),
        ended_with_marker=False,
    )


# --- per-user baseline -----------------------------------------------------


def test_baseline_is_median_iterations_excluding_abandoned() -> None:
    episodes_with_closures = [
        (_episode(T0, 2), "success"),
        (_episode(T0 + timedelta(hours=1), 4), "success"),
        (_episode(T0 + timedelta(hours=2), 6), "reformulated"),
        (_episode(T0 + timedelta(hours=3), 40), "abandoned"),  # excluded
    ]
    # Median of [2, 4, 6] — the 40-iteration abandonment must not drag it.
    assert user_baseline(episodes_with_closures) == 4.0


def test_baseline_with_no_closable_episodes_is_none() -> None:
    assert user_baseline([(_episode(T0, 5), "abandoned")]) is None


# --- return-to-cluster -----------------------------------------------------


def test_return_within_window_is_detected_per_episode() -> None:
    episodes = [
        _episode(T0, 3),
        _episode(T0 + timedelta(hours=5), 3),  # returns 5h after the first
        _episode(T0 + timedelta(days=20), 3),  # nobody returns after this
    ]
    assert returned_to_cluster(episodes, CONFIG) == [True, False, False]


def test_return_outside_window_does_not_count() -> None:
    episodes = [_episode(T0, 3), _episode(T0 + timedelta(days=10), 3)]
    assert returned_to_cluster(episodes, CONFIG) == [False, False]


# --- signals ---------------------------------------------------------------


def test_three_expensive_episodes_signal_reformulation() -> None:
    # Baseline 2.0 -> threshold 3.0 iterations; five episodes, three above.
    episodes = [
        _episode(T0 + timedelta(days=i), iterations)
        for i, iterations in enumerate([2, 4, 4, 2, 4])
    ]
    signal = detect_signal(episodes, user_baseline=2.0, config=CONFIG)
    assert signal is not None and signal.kind == "reformulation"
    assert signal.occurrences == 3


def test_two_expensive_episodes_are_not_enough() -> None:
    # Jittered spacing so the (legitimate) recurrence signal cannot fire
    # and mask the reformulation threshold under test.
    offsets_days = [0, 1, 9]
    episodes = [
        _episode(T0 + timedelta(days=offsets_days[i]), iterations)
        for i, iterations in enumerate([2, 4, 4])
    ]
    assert detect_signal(episodes, user_baseline=2.0, config=CONFIG) is None


def test_thresholds_are_relative_to_the_user_baseline() -> None:
    # The same absolute costs stop signalling when the user's own baseline
    # is high — never absolute (replay-validation skill). Jittered spacing
    # keeps recurrence out of the picture.
    offsets_days = [0, 1, 9]
    episodes = [_episode(T0 + timedelta(days=d), 4) for d in offsets_days]
    assert detect_signal(episodes, user_baseline=1.0, config=CONFIG) is not None
    assert detect_signal(episodes, user_baseline=8.0, config=CONFIG) is None


def test_stable_period_signals_recurrence_with_period_spec() -> None:
    episodes = [_episode(T0 + timedelta(days=7 * i), 2) for i in range(4)]  # weekly
    signal = detect_signal(episodes, user_baseline=4.0, config=CONFIG)
    assert signal is not None and signal.kind == "recurrence"
    assert signal.period is not None
    assert signal.period.interval == timedelta(days=7)


def test_unstable_period_is_no_recurrence() -> None:
    offsets_days = [0, 1, 9, 11, 30]
    episodes = [_episode(T0 + timedelta(days=d), 2) for d in offsets_days]
    assert detect_signal(episodes, user_baseline=4.0, config=CONFIG) is None


def test_fewer_than_three_occurrences_never_recur() -> None:
    episodes = [_episode(T0 + timedelta(days=7 * i), 2) for i in range(2)]
    assert detect_signal(episodes, user_baseline=4.0, config=CONFIG) is None
