"""Incremental intent clustering with per-user baselines.

Contract (replay-validation skill, BLUEPRINT §9 decision 2 as adopted in
the approved P1 plan):
- Embed the episode opener with a dedicated embedder behind an `Embedder`
  Protocol — centroids must survive agent-model swaps, so the embedder is
  never the agents' model. Two substrates ship: the deterministic local
  `HashedTokenEmbedder` (hashed token buckets, offline) and a real
  embedding model read from a committed vector cache
  (`cle/detect/embedders.py`).
- Incremental clustering: an opener joins the nearest centroid above the
  similarity threshold or founds a new cluster; centroids are running
  means, renormalized.
- The similarity THRESHOLD is a property of the vector space, not a global
  constant (`CLUSTER_THRESHOLD_BY_EMBEDDER`): bag-of-tokens puts
  same-domain text at ~0.2-0.4, a real sentence embedder at ~0.7-0.9, so
  one number cannot serve both. It travels with `embedder_id`, and an
  unmapped embedder falls back to the config value (sweep before trusting).

MEASURED, so no reader repeats the original assumption: swapping the
embedder is NOT "a config swap behind the same Protocol". It changes agent
identity (centroids are only meaningful in the space that produced them —
hence `TriggerSpec.embedder_id`), it requires its own threshold, and it
makes the cosine-based contradiction check unsound. See docs/METRICS.md.
- Per-user baseline: median iterations across the user's episodes,
  excluding abandoned closures (anti-Goodhart guard).
"""

import hashlib
import math
import re
import statistics
from datetime import timedelta
from typing import Protocol, Sequence

from cle.detect.episodes import Closure, DetectorConfig, Episode

Vector = tuple[float, ...]


class Embedder(Protocol):
    # Provenance of the vector space this embedder produces. Centroids are
    # only comparable within one embedder_id (see cle/detect/embedders.py).
    embedder_id: str

    def embed(self, text: str) -> Vector: ...


class HashedTokenEmbedder:
    """Deterministic, offline, dedicated — decision 2's requirements
    exactly, with fixture-grade quality. Tokens are hashed into a fixed
    number of buckets; shared vocabulary yields cosine proximity."""

    embedder_id = "stub:hashed64"

    def __init__(self, dim: int = 64) -> None:
        self._dim = dim

    def embed(self, text: str) -> Vector:
        buckets = [0.0] * self._dim
        for token in re.findall(r"[^\W_]+", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            buckets[int.from_bytes(digest[:4], "big") % self._dim] += 1.0
        norm = math.sqrt(sum(value * value for value in buckets))
        if norm == 0.0:
            return tuple(buckets)
        return tuple(value / norm for value in buckets)


def cosine(a: Vector, b: Vector) -> float:
    # Embeddings are L2-normalized (or zero), so the dot product is the
    # cosine; a zero vector never matches anything.
    return sum(x * y for x, y in zip(a, b))


# The clustering threshold is a property of the VECTOR SPACE, not a global
# default: bag-of-tokens puts same-domain text at ~0.2-0.4, a real sentence
# embedder at ~0.7-0.9, so one number cannot serve both. It therefore travels
# WITH embedder_id. An embedder absent from this map falls back to the config
# value (and should be swept before it is trusted).
CLUSTER_THRESHOLD_BY_EMBEDDER: dict[str, float] = {
    "stub:hashed64": 0.6,
    # Swept 0.60-0.95 on the realistic fixtures; 0.775 is the only region where
    # purity and recall are simultaneously non-trivial. The credible evidence is
    # the process-independent HOLDOUT (3/3 planted patterns recovered, near-
    # perfect purity), not the in-sample GDG peak — see docs/METRICS.md.
    "google:gemini-embedding-2:768": 0.775,
}


def cluster_threshold_for(embedder_id: str | None, default: float) -> float:
    return CLUSTER_THRESHOLD_BY_EMBEDDER.get(embedder_id or "", default)


class IntentClusterer:
    """Incremental clustering of episode openers for one user."""

    def __init__(self, embedder: Embedder, config: DetectorConfig) -> None:
        self._embedder = embedder
        self._threshold = cluster_threshold_for(
            getattr(embedder, "embedder_id", None), config.cluster_similarity_threshold
        )
        self.centroids: list[Vector] = []
        self._member_counts: list[int] = []

    def assign_opener(self, opener: str) -> int:
        """Return the cluster id for an opener, founding one if nothing is
        close enough. Ids are stable for the clusterer's lifetime."""
        embedding = self._embedder.embed(opener)
        best_id, best_similarity = -1, -1.0
        for cluster_id, centroid in enumerate(self.centroids):
            similarity = cosine(embedding, centroid)
            if similarity > best_similarity:
                best_id, best_similarity = cluster_id, similarity
        if best_id >= 0 and best_similarity >= self._threshold:
            self._absorb(best_id, embedding)
            return best_id
        self.centroids.append(embedding)
        self._member_counts.append(1)
        return len(self.centroids) - 1

    def assign(self, episode: Episode) -> int:
        return self.assign_opener(episode.opener)

    def _absorb(self, cluster_id: int, embedding: Vector) -> None:
        count = self._member_counts[cluster_id]
        blended = [
            (existing * count + incoming) / (count + 1)
            for existing, incoming in zip(self.centroids[cluster_id], embedding)
        ]
        norm = math.sqrt(sum(value * value for value in blended))
        self.centroids[cluster_id] = (
            tuple(blended) if norm == 0.0 else tuple(value / norm for value in blended)
        )
        self._member_counts[cluster_id] = count + 1


def returned_to_cluster(episodes: Sequence[Episode], config: DetectorConfig) -> list[bool]:
    """For each episode of ONE cluster (chronological), did the user open
    another episode in the same cluster within the reformulation window?

    This is the cluster knowledge classify_closure needs: a return marks
    the earlier episode as a failed attempt, not a closure.
    """
    flags: list[bool] = []
    for index, episode in enumerate(episodes):
        flags.append(
            any(
                timedelta(0) < later.started_at - episode.ended_at <= config.reformulation_window
                for later in episodes[index + 1 :]
            )
        )
    return flags


def user_baseline(episodes_with_closures: Sequence[tuple[Episode, Closure]]) -> float | None:
    """Median iterations across the user's episodes, excluding abandoned
    closures (replay-validation skill; recomputed daily by the pipeline).

    None when nothing survives the exclusion — a user whose entire history
    is abandonment has no meaningful baseline, and thresholds relative to
    it must not silently fall back to an absolute number.
    """
    costs = [
        episode.iterations
        for episode, closure in episodes_with_closures
        if closure != "abandoned"
    ]
    return float(statistics.median(costs)) if costs else None
