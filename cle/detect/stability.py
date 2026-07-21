"""Cluster-stability analysis — the four-contradiction taxonomy.

CLE need (stated per the governance rule): a contradictory cluster is a
"don't automate yet" signal, but environmental noise must not read as a
user contradiction — the anti-noise guard in the lineage of the
anti-Goodhart rule. Before synthesis, divergence WITHIN a cluster is
classified into:

- intra_cluster : opposite directives on the same task, close in time
                  (gap <= instability_window)      -> UNSTABLE, no candidate
- grey_zone     : divergence in the middle band
                  (instability_window .. temporal_evolution_gap) — a total
                  partition has no uncovered interval (approved adjustment
                  1); classified UNSTABLE by default: when in doubt, don't
                  automate. Band width is a calibration parameter.
- temporal      : the user changed their mind across
                  gap >= temporal_evolution_gap    -> evolution, recency
                  wins: synthesize from the post-flip segment
- world_state   : same intention, DIFFERENT frozen tool_result — the world
                  moved, not the user               -> excluded from
                  instability; a candidate may still be born

world_state preconditions (approved adjustment 2, explicit): it requires
tool_result PRESENT ON BOTH SIDES and DIFFERENT. Episodes without a tool
have no external world in the frame — their divergence can only be
intra_cluster / grey_zone / temporal, never world_state.

Adversarial guard (approved adjustment 3): a differing tool_result does
NOT blindly excuse divergence. If the directives are SEVERELY divergent
(cosine below severe_divergence_threshold — near-zero shared intent), a
genuine user contradiction may be masked by a world change; prudence
resolves the pair to UNSTABLE (missing a real contradiction is costlier
than over-flagging). Residual, documented limitation: a MODERATE
preference flip co-occurring with a world change is still excluded as
world_state — the moderate band is calibratable, not omniscient.

routing (the fourth type) is inter-cluster and lives where it always
did: false_trigger_rate.

Determinism: pure functions of the episodes and config; no LLM
judgment; reads only fixture-frozen decor; never touches answer quality.
"""

from typing import Literal, Sequence

from pydantic import BaseModel

from cle.detect.clusters import Embedder, cosine
from cle.detect.episodes import DetectorConfig, Episode
from cle.oplog import OpLog

DivergenceType = Literal["intra_cluster", "grey_zone", "temporal", "world_state"]

# Pair types that count toward instability. temporal is evolution;
# world_state is environment.
_UNSTABLE_TYPES = ("intra_cluster", "grey_zone")


class DivergentPair(BaseModel, frozen=True):
    earlier_index: int
    later_index: int
    divergence_type: DivergenceType
    directive_cosine: float
    gap_days: float


class StabilityReport(BaseModel, frozen=True):
    unstable: bool
    pairs: tuple[DivergentPair, ...]
    counts: dict[str, int]
    # When temporal evolution is present (and nothing unstable), signal
    # detection should run on episodes from this index onward (post-flip).
    stable_from_index: int


def _directive_text(episode: Episode) -> str:
    # Directives live in the follow-ups (where preferences are stated);
    # openers already agreed (same cluster). Closure markers ("thanks")
    # are ritual, not preference content — including them would inflate
    # similarity between short opposing directives and mask severity.
    from cle.detect.episodes import _contains_success_marker, DetectorConfig

    marker_cfg = DetectorConfig()
    followups = [
        m.text for m in episode.messages[1:]
        if not _contains_success_marker(m.text, marker_cfg)
    ]
    return " ".join(followups) if followups else episode.opener


def _classify_pair(
    a: Episode, b: Episode, directive_cos: float, config: DetectorConfig
) -> DivergenceType | None:
    if directive_cos >= config.directive_divergence_threshold:
        return None  # not divergent
    gap_days = abs((b.started_at - a.started_at).total_seconds()) / 86400.0

    results_a, results_b = a.tool_results, b.tool_results
    world_moved = bool(results_a) and bool(results_b) and results_a != results_b
    severe = directive_cos < config.severe_divergence_threshold
    if world_moved and not severe:
        # The one observable separating user from environment: the frozen
        # tool_result differs -> divergence attributed to the world.
        return "world_state"
    # Everything else is user-side divergence, classified by time — a
    # TOTAL partition (<= window | middle band | >= gap), no hole.
    if gap_days <= config.instability_window.total_seconds() / 86400.0:
        return "intra_cluster"
    if gap_days >= config.temporal_evolution_gap.total_seconds() / 86400.0:
        return "temporal"
    return "grey_zone"


def analyze_cluster_stability(
    episodes: Sequence[Episode],
    embedder: Embedder,
    config: DetectorConfig,
    oplog: OpLog,
    *,
    actor: str,
    cluster_label: str = "?",
) -> StabilityReport:
    """Classify intra-cluster divergence; emit one cluster_stability line.

    Verdict: unstable iff any intra_cluster or grey_zone pair exists
    (precedence rule: a single genuine flip outweighs any number of
    world_state pairs). temporal-only divergence keeps the cluster stable
    but moves the synthesis window to the post-flip segment.
    """
    ordered = sorted(episodes, key=lambda e: e.started_at)
    directives = [embedder.embed(_directive_text(e)) for e in ordered]

    pairs: list[DivergentPair] = []
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            c = cosine(directives[i], directives[j])
            kind = _classify_pair(ordered[i], ordered[j], c, config)
            if kind is not None:
                gap = (ordered[j].started_at - ordered[i].started_at).total_seconds() / 86400.0
                pairs.append(DivergentPair(
                    earlier_index=i, later_index=j, divergence_type=kind,
                    directive_cosine=round(c, 6), gap_days=round(gap, 3),
                ))

    counts = {t: 0 for t in ("intra_cluster", "grey_zone", "temporal", "world_state")}
    for pair in pairs:
        counts[pair.divergence_type] += 1
    unstable = any(counts[t] for t in _UNSTABLE_TYPES)

    # Recency weighting for temporal evolution: the post-flip segment
    # starts at the FIRST episode of the new regime (the earliest "later"
    # side of a temporal pair) — the whole recent sub-pattern, not just
    # its tail. v1 handles the single-flip case; multi-flip refinement is
    # a calibration question for real data.
    stable_from = 0
    if not unstable and counts["temporal"]:
        stable_from = min(p.later_index for p in pairs if p.divergence_type == "temporal")

    oplog.emit(
        "cluster_stability",
        actor=actor,
        cluster=cluster_label,
        unstable=unstable,
        **counts,
    )
    return StabilityReport(
        unstable=unstable, pairs=tuple(pairs), counts=counts, stable_from_index=stable_from
    )
