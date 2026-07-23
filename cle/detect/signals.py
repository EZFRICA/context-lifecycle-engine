"""Reformulation vs recurrence classification.

Contract (replay-validation skill):
- Reformulation: >=3 in-window episodes at cost >1.5x the user's baseline.
- Recurrence: stable period over >=3 occurrences; stability is a bounded
  coefficient of variation of the inter-arrival times.
- Thresholds are config with article defaults, ALWAYS relative to the
  per-user baseline, never absolute — a None baseline yields no
  reformulation signal rather than an absolute fallback.

The recurrence signal carries the PeriodSpec that becomes the temporal
half of the candidate's TriggerSpec (BLUEPRINT §4).
"""

import statistics
from typing import Literal, Sequence

from pydantic import BaseModel

from cle.detect.episodes import DetectorConfig, Episode
from cle.store.commits import PeriodSpec


class Signal(BaseModel, frozen=True):
    """Why a cluster deserves a candidate: the detected pattern and the
    occurrence count that clears the threshold."""

    kind: Literal["reformulation", "recurrence"]
    occurrences: int
    period: PeriodSpec | None = None


def detect_signal_gated(
    episodes: Sequence[Episode],
    user_baseline: float | None,
    config: DetectorConfig,
    embedder,
    oplog,
    *,
    actor: str,
    cluster_label: str = "?",
) -> Signal | None:
    """Stability-gated signal detection (the GDG-run entry point).

    Runs cluster-stability analysis FIRST: an unstable cluster (genuine
    intra-cluster contradiction, or grey-zone divergence) yields NO
    candidate — "don't automate yet". Temporal evolution restricts signal
    detection to the post-flip segment (recency wins). world_state
    divergence is environmental and gates nothing.
    """
    from cle.detect.stability import analyze_cluster_stability

    report = analyze_cluster_stability(
        episodes, embedder, config, oplog, actor=actor, cluster_label=cluster_label
    )
    if report.verdict == "unavailable":
        # NOT MEASURED — not "stable". We have no stability evidence in this
        # vector space, so we must not birth a candidate on the assumption of
        # it. Conservative by design: treating a blind check as a pass is the
        # failure mode this verdict exists to prevent.
        return None
    if report.unstable:
        return None
    window = list(episodes)[report.stable_from_index:]
    return detect_signal(window, user_baseline, config)


def detect_signal(
    episodes: Sequence[Episode], user_baseline: float | None, config: DetectorConfig
) -> Signal | None:
    """Classify one cluster's (chronological, in-window) episodes.

    Reformulation is checked first: a user hammering the same intent at
    high cost is the stronger birth signal than mere regularity, and a
    cluster can exhibit both.
    """
    if user_baseline is not None:
        threshold = config.reformulation_cost_multiplier * user_baseline
        expensive = [episode for episode in episodes if episode.iterations > threshold]
        if len(expensive) >= config.min_signal_occurrences:
            return Signal(kind="reformulation", occurrences=len(expensive))

    if len(episodes) >= config.min_signal_occurrences:
        arrivals = [episode.started_at for episode in episodes]
        intervals = [later - earlier for earlier, later in zip(arrivals, arrivals[1:])]
        mean_interval = sum(intervals, start=intervals[0] - intervals[0]) / len(intervals)
        if mean_interval.total_seconds() > 0:
            spread = statistics.pstdev(interval.total_seconds() for interval in intervals)
            variation = spread / mean_interval.total_seconds()
            if variation <= config.recurrence_tolerance:
                return Signal(
                    kind="recurrence",
                    occurrences=len(episodes),
                    period=PeriodSpec(interval=mean_interval, tolerance=config.recurrence_tolerance),
                )
    return None
