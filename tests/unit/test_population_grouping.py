"""Level 2 grouping: the engine's clusterer, at level 2's own threshold.

SCOPE: bucket 1 (embedder-agnostic). Vectors are hand-placed on the unit circle
and served by `Precomputed`, so every assertion is about the grouping rule, the
threshold and the report - never about a vector space.
"""

import math

import pytest

from cle.detect.clusters import CLUSTER_THRESHOLD_BY_EMBEDDER, IntentClusterer
from cle.detect.episodes import DetectorConfig
from cle.population.grouping import Precomputed, build_hierarchy, embed_all, group
from cle.population.naming import StubNamer
from cle.population.reader import PopulationEntry, PopulationError
from cle.population.report import discover


def _at(angle_cos: float) -> tuple[float, float]:
    """A unit vector whose cosine with (1, 0) is `angle_cos`."""
    return (angle_cos, math.sqrt(1.0 - angle_cos ** 2))


def test_an_explicit_threshold_is_honoured_even_where_the_table_knows_the_space() -> None:
    """The level-2 threshold must not be replaced by level 1's calibration.

    `stub:hashed64` IS in the table, at 0.6. Two texts at cosine 0.7 merge at the
    table's value and must stay apart at an explicit 0.78.
    """
    assert CLUSTER_THRESHOLD_BY_EMBEDDER["stub:hashed64"] == 0.6
    space = Precomputed({"a": (1.0, 0.0), "b": _at(0.7)}, "stub:hashed64")

    assert group(["a", "b"], space, 0.78) == [0, 1]
    level_one = IntentClusterer(space, DetectorConfig())
    assert [level_one.assign_opener(t) for t in ("a", "b")] == [0, 0], (
        "level 1 still takes its threshold from the table"
    )


def test_vectors_are_computed_once_per_distinct_text() -> None:
    """A live embedder is billed per call; both levels must share one pass."""
    calls: list[str] = []

    class Counting:
        embedder_id = "test:counting"

        def embed(self, text: str):
            calls.append(text)
            return (1.0, 0.0)

    space = embed_all(["x", "y", "x", "x"], Counting())
    assert sorted(calls) == ["x", "y"]
    group(["x", "y", "x"], space, 0.5)
    build_hierarchy([0, 0, 0], ["x", "y", "x"], space, 0.5)
    assert sorted(calls) == ["x", "y"]


def test_the_second_level_joins_groups_the_first_kept_apart() -> None:
    """Centroids at cosine 0.76: apart at 0.78, one family at 0.78 - 0.04."""
    space = Precomputed({"a": (1.0, 0.0), "b": _at(0.76)}, "test:2d")
    ids = group(["a", "b"], space, 0.78)
    assert ids == [0, 1]
    parents, families = build_hierarchy(ids, ["a", "b"], space, 0.78)
    assert parents[0] == parents[1]
    assert sorted(families[parents[0]]) == [0, 1]


def _entries(*triples: tuple[str, str, str]) -> list[PopulationEntry]:
    return [PopulationEntry(instance=i, agent=a, facet=f) for i, a, f in triples]


class _Space:
    embedder_id = "test:2d"

    def __init__(self, vectors) -> None:
        self.vectors = vectors

    def embed(self, text: str):
        return self.vectors[text]


def test_the_report_names_only_what_three_users_produced_and_quotes_no_facet() -> None:
    shared = "Drafts the weekly project recap for a team, with blockers and progress."
    lone = "Plans a hiking trip with routes, lodging and a packing list for the weekend."
    entries = _entries(("u1", "recap", shared), ("u2", "recap", shared),
                       ("u3", "recap", shared), ("u1", "hike", lone))
    space = _Space({shared: (1.0, 0.0), lone: (0.0, 1.0)})

    report = discover(entries, embedder=space, namer=StubNamer(), threshold=0.78,
                      instances=3, without_facet={"predates_facets": 0, "generation_failed": 0})

    assert (report.groups, report.named, report.singletons) == (2, 1, 1)
    by_size = {s.size: s for s in report.group_summaries}
    assert by_size[3].users == 3 and by_size[3].name
    assert by_size[1].name is None
    serialised = report.model_dump_json()
    assert shared not in serialised and lone not in serialised
    assert "u1" not in serialised, "instance ids must not leave the engine"


def test_a_population_embedder_that_names_no_space_is_refused() -> None:
    class Anonymous:
        def embed(self, text: str):
            return (1.0, 0.0)

    with pytest.raises(PopulationError, match="names no vector space"):
        discover(_entries(("u1", "a", "x")), embedder=Anonymous(), namer=StubNamer(),
                 threshold=0.78, instances=1, without_facet={})


def test_an_empty_population_is_an_empty_report_not_an_error() -> None:
    report = discover([], embedder=_Space({}), namer=StubNamer(), threshold=0.78,
                      instances=2, without_facet={"predates_facets": 4, "generation_failed": 0})
    assert (report.groups, report.named, report.families) == (0, 0, 0)
    assert report.without_facet["predates_facets"] == 4
