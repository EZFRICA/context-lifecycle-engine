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

Two gates enforced here:
- PROVENANCE. Routing compares the candidate centroid against every
  incumbent's, and those cosines only mean something inside ONE vector
  space, so a cross-space comparison raises `SpaceMismatchError` rather
  than returning a plausible-looking number.
- CAPABILITY (stage 2 of the tool gating; stage 1 is in the resolver). An
  episode that REQUIRED a tool is captured only if the candidate mounts
  it. Such episodes stay in the DENOMINATOR, so capture drops honestly
  instead of hiding the capability gap. `tool_result` is read as frozen
  decor and never scored — asserting it correct would be answer-quality
  territory (invariant 5).
"""

import statistics
import time
from typing import Sequence

from pydantic import BaseModel

from cle.detect.clusters import Embedder, IntentClusterer, cosine, returned_to_cluster
from cle.detect.episodes import DetectorConfig, Episode, Message, classify_closure, segment
from cle.oplog import OpLog
from cle.store.commits import PreEvidence, TriggerSpec
from cle.detect.embedders import SpaceMismatchError


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


def _require_operand_space(operand_space: str | None, trigger, what: str) -> None:
    """Refuse a comparison whose two operands come from different vector spaces.

    Placed AT each comparison, not only at the function entry. The entry gate
    checks the embedder handed in, which covers the three sites below only
    because every centroid reaching them happens to come from it today — a
    property of the current flow, not of the code. These read the provenance of
    the operand actually being compared, so they survive a new path being added.

    Cost: three string comparisons per episode, against a 768-dimension dot
    product measured at ~21 us. Immeasurable by comparison.
    """
    if operand_space != trigger.embedder_id:
        raise SpaceMismatchError(
            f"{what} comes from {operand_space!r} but the trigger centroid comes "
            f"from {trigger.embedder_id!r}; a cosine across two spaces returns a "
            "number that looks fine and means nothing"
        )


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
    mounted_tools: frozenset[str] = frozenset(),
) -> ReplayOutcome:
    """Replay the window against topology ∪ {candidate}; report the trigger's
    retrospective behavior. Raises ReplayError (logged, nothing written)
    when the window has nothing to validate against."""
    started = time.monotonic()
    try:
        outcome = _replay(
            trigger, messages, window_label, existing_triggers, embedder, config, mounted_tools
        )
        # Closure counts are `dict[str, int]` whose keys are closure tags, not
        # parameter names; the checker has to assume an `int` could land on a
        # named parameter of `emit`. Runtime-correct.
        # pyrefly: ignore[bad-argument-type]
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
    mounted_tools: frozenset[str],
) -> ReplayOutcome:
    # Provenance gate: routing compares the candidate centroid against every
    # incumbent centroid. Those cosines are only meaningful inside ONE vector
    # space, so a cross-space comparison raises instead of returning a number
    # that looks fine and means nothing.
    for incumbent in existing_triggers:
        trigger.require_same_space(incumbent)

    # The gate above compares two STORED centroids and cannot see the embedder
    # actually running, which is the gap this check closes: under a different
    # --embedder, `embedder.embed(...)` below produces vectors from one space
    # while `trigger.centroid` comes from another, and every cosine in this
    # function would cross them silently (selecting target_cluster, computing
    # capture, and beating incumbents — three sites, not one).
    #
    # Guard on IDENTITY, not on dimension: two distinct real spaces of equal
    # width would pass a length check and mean nothing.
    runtime_space = getattr(embedder, "embedder_id", None)
    if runtime_space != trigger.embedder_id:
        raise SpaceMismatchError(
            f"replay runs on embedder {runtime_space!r} but the trigger centroid "
            f"comes from {trigger.embedder_id!r}; a centroid is only meaningful in "
            "the space that produced it — rebuild the spec under this embedder"
        )

    episodes = segment(list(messages), config)
    if not episodes:
        raise ReplayError("replay window contains no episodes")

    # Re-cluster the window; the candidate's cluster is the one whose
    # centroid sits closest to the trigger centroid.
    clusterer = IntentClusterer(embedder, config)
    assignments = [clusterer.assign(episode) for episode in episodes]
    # Site 1 of 3. The entry gate checks the embedder passed IN; this checks the
    # provenance of the OPERAND actually compared. They differ the day a centroid
    # reaches this function by another path — which is exactly why the entry gate
    # alone is a property of the current flow, not of the code.
    _require_operand_space(clusterer.embedder_id, trigger, "clusterer centroid")
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
        # Capability gating (approved design): an episode that REQUIRED a
        # tool is only captured if the candidate mounts it. Such episodes
        # stay in the denominator — capture drops honestly rather than
        # hiding the capability gap.
        if episode.required_tool is not None and episode.required_tool not in mounted_tools:
            return False
        # Site 2 of 3: the freshly embedded opener, checked against the centroid.
        _require_operand_space(
            getattr(embedder, "embedder_id", None), trigger, "opener embedding"
        )
        opener_embedding = embedder.embed(episode.opener)
        candidate_similarity = cosine(opener_embedding, trigger.centroid)
        if candidate_similarity < config.cluster_similarity_threshold:
            return False
        # Site 3 of 3: each incumbent centroid carries its own provenance.
        for incumbent in existing_triggers:
            _require_operand_space(incumbent.embedder_id, trigger, "incumbent centroid")
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
