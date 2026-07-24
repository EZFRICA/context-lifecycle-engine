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
    """Why a cluster deserves a candidate: the detected pattern, the occurrence
    count that clears the threshold, and the PROVENANCE of the checks that ran.

    `stability` records what the contradiction check actually concluded:
    "stable" (it ran and found no contradiction) or "unavailable" (it could not
    run in this vector space). The distinction is the whole point — a candidate
    born with `stability="unavailable"` carries a DISCLOSED GAP to the human
    gate, and must never be presented as one whose cluster was checked and
    found clean. A signal is never constructed with stability="unstable":
    an unstable cluster is vetoed and yields no candidate at all.
    """

    kind: Literal["reformulation", "recurrence"]
    occurrences: int
    period: PeriodSpec | None = None
    stability: Literal["stable", "unavailable"] = "stable"


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

    The stability check is a safety VETO, never a precondition for a candidate
    to exist: an unstable cluster (genuine intra-cluster contradiction, or
    grey-zone divergence) yields NO candidate — "don't automate yet". Temporal
    evolution restricts signal detection to the post-flip segment (recency
    wins). world_state divergence is environmental and gates nothing.

    When the check could not run at all (`verdict == "unavailable"`, e.g. a
    vector space where directive-divergence-by-cosine says nothing), detection
    PROCEEDS and the candidate is born carrying `stability="unavailable"` in
    its provenance, surfaced to the human at the override gate.

    Why not block: making the check's ABSENCE a hard block would give it weight
    it never had, and would stop the first pillar producing anything at all —
    a system that detects nothing is worse than one that proposes with a
    documented gap. Compare the failure modes: treating "unavailable" as a pass
    risks a candidate born on a contradictory cluster, which the human gate AND
    the trial both catch downstream; treating it as a block kills detection
    outright, with nothing to compensate. The non-measurement is still never a
    verdict — it is a DISCLOSED GAP rather than a silent pass.
    """
    from cle.detect.stability import analyze_cluster_stability

    report = analyze_cluster_stability(
        episodes, embedder, config, oplog, actor=actor, cluster_label=cluster_label
    )
    if report.verdict == "unstable":
        return None  # the veto: a self-contradicting cluster is not automated
    window = list(episodes)[report.stable_from_index:]
    signal = detect_signal(window, user_baseline, config)
    if signal is None:
        return None
    # Carry what the check actually concluded — never "stable" when it could
    # not run. This is the field the human override gate reads.
    return signal.model_copy(update={"stability": report.verdict})


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
