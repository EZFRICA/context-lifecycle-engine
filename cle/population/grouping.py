"""Clio stages 2 and 4: group the facets, then group the groups.

THE ALGORITHM IS THE ENGINE'S. `IntentClusterer` does incremental threshold
clustering of one user's episode openers; the same procedure over facet vectors
is level 2's grouping. It is reused rather than reimplemented, so a change to the
engine's clustering reaches level 2 at once instead of drifting away from it.

THE THRESHOLD IS EXPLICIT. Level 1 resolves its threshold from a per-space table
(`CLUSTER_THRESHOLD_BY_EMBEDDER`), calibrated on episode OPENERS. Facets are a
different object, and the right value depends on the corpus: 0.78 grouped the
planted intents of the synthetic GDG corpus best and leaves most real groups as
singletons. So level 2 passes its threshold explicitly and `IntentClusterer`
honours it, whatever the table says for that space.

Vectors are computed ONCE per distinct text (`embed_all`) and served from memory
to both levels, so a live embedder is billed once, not twice.
"""

import collections
from typing import Mapping, Sequence

from cle.detect.clusters import Embedder, IntentClusterer, Vector
from cle.detect.episodes import DetectorConfig

#: How much looser the second level is than the first. No corpus here has a
#: labelled hierarchy, so it is chosen on a structural rule - reduce the count
#: without one family swallowing the corpus. Measured sweep (docs/FINDINGS.md
#: §6d): at a gap of 0.10 WildChat put 106 of its 116 groups in one family; 0.04
#: keeps the largest family under a third on both real corpora.
LEVEL2_LOOSER = 0.04


class Precomputed:
    """An embedder that serves vectors already computed, addressed by text."""

    def __init__(self, vectors: Mapping[str, Vector], embedder_id: str) -> None:
        self._vectors = dict(vectors)
        self.embedder_id = embedder_id

    def embed(self, text: str) -> Vector:
        return self._vectors[text]


def embed_all(texts: Sequence[str], embedder: Embedder) -> Precomputed:
    """One call per DISTINCT text, then served from memory."""
    vectors = {text: tuple(embedder.embed(text)) for text in dict.fromkeys(texts)}
    return Precomputed(vectors, getattr(embedder, "embedder_id", "") or "")


def group(texts: Sequence[str], space: Embedder, threshold: float) -> list[int]:
    """A group id per text, at exactly `threshold`."""
    clusterer = IntentClusterer(space, DetectorConfig(), threshold=threshold)
    return [clusterer.assign_opener(text) for text in texts]


def centroid(vectors: Sequence[Vector]) -> Vector:
    """The mean of unit vectors, renormalised onto the unit sphere."""
    mean = [sum(column) / len(column) for column in zip(*vectors)]
    norm = sum(value * value for value in mean) ** 0.5
    return tuple(value / norm for value in mean) if norm else tuple(mean)


def build_hierarchy(ids: Sequence[int], texts: Sequence[str], space: Embedder,
                    threshold: float, looser: float = LEVEL2_LOOSER,
                    ) -> tuple[list[int], dict[int, list[int]]]:
    """Clio's stage 4: cluster the group CENTROIDS, giving each group a parent.

    Returns the parent id of every text, and the children of every parent.
    """
    by_group: dict[int, list[str]] = collections.defaultdict(list)
    for gid, text in zip(ids, texts):
        by_group[gid].append(text)
    order = sorted(by_group)
    # Keys are synthetic because the clusterer addresses vectors by text.
    keys = {gid: f"__group_{gid}__" for gid in order}
    parents_space = Precomputed(
        {keys[g]: centroid([space.embed(t) for t in by_group[g]]) for g in order},
        getattr(space, "embedder_id", "") or "",
    )
    parent_ids = group([keys[g] for g in order], parents_space, max(0.0, threshold - looser))
    parent_of = dict(zip(order, parent_ids))
    families: dict[int, list[int]] = collections.defaultdict(list)
    for gid, pid in parent_of.items():
        families[pid].append(gid)
    return [parent_of[g] for g in ids], dict(families)
