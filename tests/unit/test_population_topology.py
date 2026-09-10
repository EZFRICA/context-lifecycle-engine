"""The facet in `topology.yaml`, and `reader.py`, the only way level 2 reads it.

SCOPE: bucket 1 (embedder-agnostic). The embedding configuration is recorded as
a key and compared, never used to embed anything.
"""

import io
from pathlib import Path

import pytest
import yaml

from cle.detect.embedders import EmbeddingConfig, StubEmbedder, embedding_config_for
from cle.lifecycle.reasons import FreeTextInTopologyError
from cle.lifecycle.topology import FacetNotAtBirthError, current_agents, write_topology
from cle.oplog import OpLog
from cle.population.facet import build_facet
from cle.population.reader import MixedSpaceError, PopulationError, read_population
from cle.store.backends import open_store

TEXT = "Drafts the weekly project recap for a team, with blockers and progress."
BIRTH = {"pre_evidence": {"capture_rate": 1.0}}
LATER = {"evidence": {"cost_ratio": 0.6}}


def _facet(text: str = TEXT):
    return build_facet(text, sources=[], generator_id="test:v1")


def _write(state: Path, agent: str, *, cause=BIRTH, embedding=None, **kwargs) -> str:
    return write_topology(
        backend=open_store(state), path=state / "topology.yaml", agent=agent,
        state="candidate", image_hash="a" * 64, cause=cause, oplog=OpLog(io.StringIO()),
        actor="human:test", embedding=embedding or embedding_config_for(StubEmbedder()),
        **kwargs,
    )


def test_a_facet_is_stored_typed_and_marked_present(tmp_path) -> None:
    _write(tmp_path, "recap", facet=_facet())
    entry = current_agents(open_store(tmp_path))["recap"]
    assert entry["facet_status"] == "present"
    assert entry["facet"] == {"text": TEXT, "generator_id": "test:v1"}
    assert yaml.safe_load((tmp_path / "topology.yaml").read_text())["agents"]["recap"]["facet"]


def test_prose_passed_as_a_facet_is_refused(tmp_path) -> None:
    with pytest.raises(FreeTextInTopologyError, match="must be a cle.population.facet.Facet"):
        _write(tmp_path, "recap", facet=TEXT)


def test_prose_stuffed_into_the_cause_is_refused(tmp_path) -> None:
    with pytest.raises(FreeTextInTopologyError, match="cause\\['facet'\\]"):
        _write(tmp_path, "recap", cause={**BIRTH, "facet": TEXT})


def test_present_cannot_be_declared_without_a_facet(tmp_path) -> None:
    with pytest.raises(ValueError, match="no facet to store"):
        _write(tmp_path, "recap", facet_status="present")


@pytest.mark.parametrize("late", [{"facet": "make"}, {"facet_status": "generation_failed"}])
def test_a_facet_is_settled_at_birth_and_never_again(tmp_path, late) -> None:
    _write(tmp_path, "recap")  # born before facets: no status at all
    if "facet" in late:
        late = {"facet": _facet()}
    with pytest.raises(FacetNotAtBirthError):
        _write(tmp_path, "recap", cause=LATER, **late)


def test_a_tag_move_carries_the_facet_forward_untouched(tmp_path) -> None:
    _write(tmp_path, "recap", facet=_facet())
    _write(tmp_path, "failed", facet_status="generation_failed")
    _write(tmp_path, "legacy")
    for agent in ("recap", "failed", "legacy"):
        _write(tmp_path, agent, cause=LATER)
    agents = current_agents(open_store(tmp_path))
    assert agents["recap"]["facet"]["text"] == TEXT
    assert agents["failed"]["facet_status"] == "generation_failed"
    assert "facet_status" not in agents["legacy"], "an agent born before facets never gets one"


# --- reader.py ---------------------------------------------------------------

def test_the_reader_tells_the_three_cases_apart(tmp_path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    _write(one, "recap", facet=_facet())
    _write(one, "failed", facet_status="generation_failed")
    _write(two, "legacy")

    data = read_population([one, two])

    assert data.instances == 2
    assert [(e.agent, e.facet) for e in data.entries] == [("recap", TEXT)]
    assert data.without_facet == {"predates_facets": 1, "generation_failed": 1}
    assert data.entries[0].instance not in (str(one), str(two)), "a path would name a user"


def test_topologies_born_in_different_spaces_cannot_be_aggregated(tmp_path) -> None:
    other = EmbeddingConfig(embedder_id="google:gemini-embedding-2:768",
                            cluster_threshold=0.775, calibration="test")
    _write(tmp_path / "stub", "recap", facet=_facet())
    _write(tmp_path / "gemini", "recap", facet=_facet(), embedding=other)
    with pytest.raises(MixedSpaceError):
        read_population([tmp_path / "stub", tmp_path / "gemini"])


def test_the_same_instance_given_twice_is_refused(tmp_path) -> None:
    """Counting one user twice is how a k-anonymity floor is bypassed."""
    _write(tmp_path, "recap", facet=_facet())
    with pytest.raises(PopulationError, match="already given"):
        read_population([tmp_path, tmp_path])


def test_a_directory_with_no_topology_is_an_error_not_an_empty_user(tmp_path) -> None:
    with pytest.raises(PopulationError, match="holds no topology"):
        read_population([tmp_path])
