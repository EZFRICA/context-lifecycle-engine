"""Build stage 2 — replay validation.

Contract (replay-validation skill, BLUEPRINT §3.2, invariant 5):
Replay answers ONE question: would this candidate's trigger have fired on
the right past episodes? It can never rate answer quality — yesterday's
user cannot score an alternative answer. Outputs are `PreEvidence`
(capture_rate, false_trigger_rate, historical_cost, window) and the type
system keeps them out of promotion paths.
- false_trigger_rate MUST be computed wherever capture_rate is (replay
  out-of-cluster traffic too).
- Determinism: same window + same candidate => same report (property test).
- Replay touches no live traffic; no store writes except the build log.

P1 routing scope: the semantic half of the trigger (cosine against the
centroid, competing with the existing topology). A period, when present,
is carried into the image untested by replay — evaluating temporal fit
retrospectively needs the v2 scheduler model, and pretending otherwise
would overstate what replay proved.
"""

import statistics
import time
from typing import Sequence

from pydantic import BaseModel

from cle.detect.clusters import Embedder, IntentClusterer, cosine, returned_to_cluster
from cle.detect.episodes import DetectorConfig, Episode, Message, classify_closure, segment
from cle.oplog import OpLog
from cle.store.commits import PreEvidence, TriggerSpec


class ReplayError(Exception):
    """Stage-2 failure: the window cannot validate anything (no episodes,
    or no in-cluster traffic to measure capture against)."""


class ReplayOutcome(BaseModel, frozen=True):
    """Internal carrier for stage 3 — NOT an evidence type.

    pre_evidence is the contractual replay report; in_cluster_openers are
    the probe-set raw material (§9 decision 3) the assembler freezes.
    """

    pre_evidence: PreEvidence
    in_cluster_openers: tuple[str, ...]
    # Closure mix of the in-cluster episodes — the closure_distribution
    # measurement (P1 arbitration): how the cluster's episodes ended is
    # article-9 material and the sanity check on the abandoned-exclusion.
    closure_counts: dict[str, int]


def replay_validate(
    *,
    trigger: TriggerSpec,
    messages: Sequence[Message],
    window_label: str,
    existing_triggers: Sequence[TriggerSpec],
    embedder: Embedder,
    config: DetectorConfig,
    oplog: OpLog,
    actor: str,
) -> ReplayOutcome:
    """Replay the window against topology ∪ {candidate}; report the trigger's
    retrospective behavior. Raises ReplayError (logged, nothing written)
    when the window has nothing to validate against."""
    started = time.monotonic()
    try:
        outcome = _replay(trigger, messages, window_label, existing_triggers, embedder, config)
        oplog.emit("closure_distribution", actor=actor, **outcome.closure_counts)
        return outcome
    except ReplayError:
        oplog.emit(
            "build",
            actor=actor,
            stage="replay",
            outcome="failed",
            latency_ms=round((time.monotonic() - started) * 1000, 3),
        )
        raise


def _replay(
    trigger: TriggerSpec,
    messages: Sequence[Message],
    window_label: str,
    existing_triggers: Sequence[TriggerSpec],
    embedder: Embedder,
    config: DetectorConfig,
) -> ReplayOutcome:
    episodes = segment(list(messages), config)
    if not episodes:
        raise ReplayError("replay window contains no episodes")

    # Re-cluster the window; the candidate's cluster is the one whose
    # centroid sits closest to the trigger centroid.
    clusterer = IntentClusterer(embedder, config)
    assignments = [clusterer.assign(episode) for episode in episodes]
    target_cluster = max(
        range(len(clusterer.centroids)),
        key=lambda cluster_id: cosine(clusterer.centroids[cluster_id], trigger.centroid),
    )
    in_cluster = [e for e, c in zip(episodes, assignments) if c == target_cluster]
    out_of_cluster = [e for e, c in zip(episodes, assignments) if c != target_cluster]
    if not in_cluster:
        raise ReplayError("no in-cluster episodes in the replay window")

    # Routing: the candidate fires when it clears the similarity bar AND
    # beats every existing trigger — ties go to the incumbent, so a
    # candidate can never silently annex already-routed traffic.
    def candidate_fires(episode: Episode) -> bool:
        opener_embedding = embedder.embed(episode.opener)
        candidate_similarity = cosine(opener_embedding, trigger.centroid)
        if candidate_similarity < config.cluster_similarity_threshold:
            return False
        return all(
            candidate_similarity > cosine(opener_embedding, incumbent.centroid)
            for incumbent in existing_triggers
        )

    captured_in = sum(1 for episode in in_cluster if candidate_fires(episode))
    captured_out = sum(1 for episode in out_of_cluster if candidate_fires(episode))

    # historical_cost: what the cluster costs under the CURRENT topology —
    # the numeric justification of the birth. Abandoned episodes are
    # excluded (anti-Goodhart guard), using the same provisional-baseline
    # bootstrap as the detector: closure needs a baseline, so the first
    # pass uses the unclassified median.
    return_flags = returned_to_cluster(in_cluster, config)
    provisional_baseline = float(statistics.median(e.iterations for e in in_cluster))
    closures = [
        classify_closure(
            episode, returned_to_cluster=flag, user_baseline=provisional_baseline, config=config
        )
        for episode, flag in zip(in_cluster, return_flags)
    ]
    countable = [
        episode.iterations
        for episode, closure in zip(in_cluster, closures)
        if closure != "abandoned"
    ]
    if not countable:
        raise ReplayError("every in-cluster episode classified abandoned; no cost baseline")

    pre_evidence = PreEvidence(
        capture_rate=captured_in / len(in_cluster),
        false_trigger_rate=(captured_out / len(out_of_cluster)) if out_of_cluster else 0.0,
        historical_cost=statistics.fmean(countable),
        window=window_label,
        semantic_trigger_tested=True,
        period_tested=False,  # see module docstring: v2 scheduler model
    )
    return ReplayOutcome(
        pre_evidence=pre_evidence,
        in_cluster_openers=tuple(episode.opener for episode in in_cluster),
        closure_counts={
            label: sum(1 for closure in closures if closure == label)
            for label in ("success", "reformulated", "abandoned")
        },
    )
