"""Embedder and clustering determinism — centroids are trigger material.

If clustering is not deterministic, replay (same window + same candidate
=> same report) cannot be. Property-tested before the implementation.
"""

from hypothesis import given
from hypothesis import strategies as st

from cle.detect.clusters import HashedTokenEmbedder, IntentClusterer, cosine
from cle.detect.episodes import DetectorConfig

texts = st.text(min_size=1, max_size=60)


@given(texts)
def test_embedding_is_deterministic(text: str) -> None:
    embedder = HashedTokenEmbedder()
    assert embedder.embed(text) == embedder.embed(text)


@given(texts)
def test_embedding_is_normalized_or_zero(text: str) -> None:
    vector = HashedTokenEmbedder().embed(text)
    norm = sum(v * v for v in vector) ** 0.5
    assert norm == 0.0 or abs(norm - 1.0) < 1e-9


@given(st.lists(texts, min_size=1, max_size=12))
def test_clustering_is_deterministic_over_input(openers: list[str]) -> None:
    config = DetectorConfig()

    def run() -> list[int]:
        clusterer = IntentClusterer(HashedTokenEmbedder(), config)
        return [clusterer.assign_opener(opener) for opener in openers]

    assert run() == run()


def test_identical_openers_share_a_cluster() -> None:
    clusterer = IntentClusterer(HashedTokenEmbedder(), DetectorConfig())
    first = clusterer.assign_opener("write the weekly recap of my project")
    second = clusterer.assign_opener("write the weekly recap of my project")
    assert first == second


def test_disjoint_vocabulary_separates_clusters() -> None:
    clusterer = IntentClusterer(HashedTokenEmbedder(), DetectorConfig())
    recap = clusterer.assign_opener("write the weekly recap of my project")
    fridge = clusterer.assign_opener("debug kubernetes ingress timeout")
    assert recap != fridge


def test_cosine_bounds() -> None:
    embedder = HashedTokenEmbedder()
    a = embedder.embed("weekly recap for the team")
    b = embedder.embed("weekly recap for the project")
    assert -1.0 - 1e-9 <= cosine(a, b) <= 1.0 + 1e-9
