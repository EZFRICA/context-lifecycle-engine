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
than over-flagging).

KNOWN LIMITATION — moderate-band contradictions on tool-bearing clusters
are NOT detected in v1. A MODERATE preference flip (directive cosine
between severe_divergence_threshold and directive_divergence_threshold)
co-occurring with a world change is still classified world_state and
excluded. This is not a threshold we can safely move: on the GDG fixture
every divergent pair in the tool-bearing `events` cluster sits at exactly
one cosine (band width 0.0000), so the divergence measure cannot separate
a mild contradiction from lexically diverse but consistent follow-ups —
any threshold placed inside that degenerate bin is arbitrary. Closing the
blind spot needs a finer embedder (a real divergence spread) AND a fixture
that plants a moderate contradiction in a tool-bearing cluster; see
docs/METRICS.md (fixture debt). v1 SURFACES the condition instead of
guessing — see the resolution diagnostic below.

Resolution diagnostic (Option B extended): when a cluster's divergent
cosines concentrate in a band narrower than config.degenerate_band_width
(with at least degenerate_min_pairs to be meaningful), the report carries
resolution="degenerate" and the band width. Such a cluster is neither
stable nor unstable — it is UNRESOLVABLE at the current measurement
resolution. The flag is DIAGNOSTIC ONLY: it is logged, it never blocks,
and `unstable` is still computed. Rationale (same principle as
PreEvidence != Evidence): a weak measurement must not masquerade as a
strong verdict.

world_state attribution: the log line carries, permanently, how many
world_state pairs would have been intra_cluster with an identical
tool_result (ws_would_be_intra) and what fraction of all divergent pairs
the world_state exclusion absorbs (ws_share_pct) — so the exclusion's
reach stays visible rather than hidden inside a single count.

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
Verdict = Literal["stable", "unstable", "unavailable"]

# The spaces the bag-of-tokens divergence heuristic was CALIBRATED FOR. This is
# not a soundness property: R6 showed the heuristic only appeared to work there
# by lexical coincidence — opposing instructions happen to share few tokens —
# not because cosine measures contradiction. In a real semantic space it scores
# the planted OPPOSING directives at 0.62-0.86 (they ARE about the same thing),
# detects nothing, and must report `unavailable` rather than a reassuring
# "stable".
#
# CLE need: a NON-MEASUREMENT MUST NEVER MASQUERADE AS A VERDICT — the same
# principle as PreEvidence != Evidence and the `degenerate` resolution flag.
# Replacing cosine with a signed/entailment operator is its own run.
DIVERGENCE_HEURISTIC_CALIBRATED_FOR = frozenset({"stub:hashed64"})

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
    # THREE-valued outcome. `unstable` is kept for existing callers but is
    # meaningless when verdict == "unavailable": consumers MUST branch on
    # `verdict` and treat "unavailable" as NOT MEASURED, never as stable.
    verdict: Verdict = "stable"
    unstable: bool
    pairs: tuple[DivergentPair, ...]
    counts: dict[str, int]
    # When temporal evolution is present (and nothing unstable), signal
    # detection should run on episodes from this index onward (post-flip).
    stable_from_index: int
    # Resolution diagnostic — orthogonal to the stable/unstable axis and
    # never blocking. "degenerate" means the divergent cosines are too
    # concentrated for the measure to resolve a verdict (band_width < the
    # configured floor); the verdict above is then unreliable by nature.
    resolution: Literal["resolved", "degenerate"] = "resolved"
    band_width: float = 0.0
    # How far the world_state exclusion reaches (permanent instrumentation):
    # ws_would_be_intra = world_state pairs that would be intra_cluster with
    # an identical tool_result; ws_share_pct = world_state / all divergent.
    ws_would_be_intra: int = 0
    ws_share_pct: float = 0.0


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
    # Soundness gate: in a space where cosine does not separate opposing
    # directives, this classifier measures NOTHING. Report that, rather than
    # returning "stable" and letting a blind check read as reassurance.
    embedder_id = getattr(embedder, "embedder_id", None)
    if embedder_id not in DIVERGENCE_HEURISTIC_CALIBRATED_FOR:
        empty = {t: 0 for t in ("intra_cluster", "grey_zone", "temporal", "world_state")}
        oplog.emit(
            "cluster_stability",
            actor=actor,
            cluster=cluster_label,
            verdict="unavailable",
            unstable=False,
            reason="the bag-of-tokens divergence heuristic is not calibrated for "
                   f"embedder_id={embedder_id!r}",
            resolution="unavailable",
            band_width=0.0,
            divergent_pairs=empty,
            world_state_attribution={"ws_would_be_intra": 0, "ws_share_pct": 0.0},
        )
        return StabilityReport(
            verdict="unavailable", unstable=False, pairs=(), counts=empty,
            stable_from_index=0, resolution="degenerate", band_width=0.0,
        )

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

    # world_state attribution (permanent instrumentation): of the pairs the
    # world_state excuse absorbs, how many are intra_cluster by time alone
    # (would be UNSTABLE with an identical tool_result), and what share of
    # ALL divergent pairs the exclusion reaches.
    window_days = config.instability_window.total_seconds() / 86400.0
    ws_would_be_intra = sum(
        1 for p in pairs if p.divergence_type == "world_state" and p.gap_days <= window_days
    )
    total_divergent = len(pairs)
    ws_share_pct = round(100.0 * counts["world_state"] / total_divergent, 1) if total_divergent else 0.0

    # Resolution diagnostic: is the divergence measure even able to resolve
    # a verdict here? A near-zero span across enough pairs means the cosine
    # cannot separate contradiction from lexical noise. Diagnostic only —
    # it never touches `unstable`.
    cosines = [p.directive_cosine for p in pairs]
    band_width = round(max(cosines) - min(cosines), 6) if cosines else 0.0
    degenerate = (
        total_divergent >= config.degenerate_min_pairs
        and band_width < config.degenerate_band_width
    )
    resolution: Literal["resolved", "degenerate"] = "degenerate" if degenerate else "resolved"

    oplog.emit(
        "cluster_stability",
        actor=actor,
        cluster=cluster_label,
        verdict="unstable" if unstable else "stable",
        unstable=unstable,
        resolution=resolution,
        band_width=band_width,
        divergent_pairs=counts,
        world_state_attribution={
            "ws_would_be_intra": ws_would_be_intra,
            "ws_share_pct": ws_share_pct,
        },
    )
    return StabilityReport(
        verdict="unstable" if unstable else "stable",
        unstable=unstable,
        pairs=tuple(pairs),
        counts=counts,
        stable_from_index=stable_from,
        resolution=resolution,
        band_width=band_width,
        ws_would_be_intra=ws_would_be_intra,
        ws_share_pct=ws_share_pct,
    )
