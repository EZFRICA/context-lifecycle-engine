"""The dashboard must agree with `topology.yaml`, field by field.

`reads.topology` builds its payload from an explicit whitelist, so a field added
to the topology record is simply absent from the API until someone adds it in
two places. Nothing raises when that happens: every other field matches and the
missing one reads as `None`.

A hand comparison catches that once. This file catches it every run.

SCOPE: bucket 1 (embedder-agnostic). The topology is written under the stub, but
nothing here asserts anything about the space itself, only that both readers
report the same one.
"""

from __future__ import annotations

import io

import pytest
import yaml

from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.embedders import embedding_config_for
from cle.lifecycle.reasons import TopologyReason
from cle.lifecycle.topology import write_topology
from cle.oplog import OpLog
from cle.store.backends import FileStore
from cle.store.commits import Evidence, PreEvidence

from tests.unit.test_runtime import _build_image

#: Every field the record carries that a reader of the dashboard needs in order
#: to interpret what they are looking at. Enumerated rather than derived,
#: because the point of the test is that the API's own enumeration drifted.
RECORD_FIELDS = ("version", "embedding")
AGENT_FIELDS = ("state", "image", "cause")


@pytest.fixture()
def populated(tmp_path):
    """A state with three agents, one per cause kind, and two versions."""
    state = tmp_path / "state"
    backend = FileStore(state / "store")
    oplog = OpLog(io.StringIO())
    image = _build_image(backend, oplog)
    topo = state / "topology.yaml"
    born_in = embedding_config_for(HashedTokenEmbedder())

    write_topology(
        backend=backend, path=topo, agent="recap", state="candidate",
        image_hash=image.hash,
        cause={"pre_evidence": PreEvidence(
            capture_rate=0.9, false_trigger_rate=0.02,
            historical_cost=4.0, window="30d",
        ).model_dump()},
        oplog=oplog, actor="human:test", embedding=born_in,
    )
    write_topology(
        backend=backend, path=topo, agent="recap", state="ephemeral",
        image_hash=image.hash,
        cause={"evidence": Evidence(
            cost_ratio=0.5, occurrences=4, closure_tags=("success",) * 4,
        ).model_dump()},
        oplog=oplog, actor="human:test",
    )
    write_topology(
        backend=backend, path=topo, agent="recap", state="trial",
        image_hash=image.hash, cause={}, oplog=oplog, actor="human:test",
        reason=TopologyReason(reason="cost_regression"),
    )
    return state, topo


def test_every_record_field_the_api_serves_matches_the_file(populated) -> None:
    """Version and embedding, the two topology-scope fields.

    `embedding` is asserted by name rather than by iterating the payload, so
    removing it from the whitelist fails here instead of silently shrinking what
    is compared.
    """
    from dashboard.backend import reads

    state, topo = populated
    api = reads.topology(state)
    disk = yaml.safe_load(topo.read_text())

    for field in RECORD_FIELDS:
        assert field in api, f"the API payload dropped {field!r}"
        assert api[field] == disk.get(field), (
            f"{field}: API says {api[field]!r}, the file says {disk.get(field)!r}"
        )

    assert api["embedding"] is not None, (
        "the vector space is None in the API; a reader cannot tell which space "
        "these states were born in"
    )


def test_every_agent_field_matches_the_file(populated) -> None:
    """State, image and the whole cause dict, per agent.

    The cause is compared as a dict, not by a summarising `cause_kind`: the
    dashboard also derives `cause_kind` for its cards, and comparing only the
    derived value would pass while the underlying evidence differed.
    """
    from dashboard.backend import reads

    state, topo = populated
    api_agents = reads.topology(state)["agents"]
    disk_agents = yaml.safe_load(topo.read_text())["agents"]

    assert set(api_agents) == set(disk_agents)
    for name in sorted(disk_agents):
        for field in AGENT_FIELDS:
            assert api_agents[name][field] == disk_agents[name][field], (
                f"{name}.{field}: API {api_agents[name][field]!r} != "
                f"file {disk_agents[name][field]!r}"
            )


def test_the_closed_vocabulary_reason_survives_the_round_trip(populated) -> None:
    """The reason is the field level 2 reads most; it must not be reshaped.

    The third write descends on `cost_regression`. If the dashboard rendered a
    summary instead of the value, a population report built on the API would be
    counting something the topology never said.
    """
    from dashboard.backend import reads

    state, topo = populated
    api = reads.topology(state)["agents"]["recap"]
    disk = yaml.safe_load(topo.read_text())["agents"]["recap"]

    assert api["cause"]["reason"] == "cost_regression" == disk["cause"]["reason"]
    assert api["state"] == "trial" == disk["state"]


def test_the_version_list_matches_the_number_of_writes(populated) -> None:
    from dashboard.backend import reads

    state, _ = populated
    assert reads.topology_versions(state) == [1, 2, 3]
    assert reads.topology(state)["version"] == 3


def test_an_older_version_is_served_as_it_was_written(populated) -> None:
    """Not only the head. A history nobody can read back is not a history."""
    from dashboard.backend import reads

    state, _ = populated
    first = reads.topology(state, version=1)

    assert first["version"] == 1
    assert first["agents"]["recap"]["state"] == "candidate"
    assert "pre_evidence" in first["agents"]["recap"]["cause"]
    assert first["embedding"]["embedder_id"] == "stub:hashed64"


# ── the payload shape must not depend on whether the store has data ─────────

def test_the_empty_payload_has_the_same_keys_as_the_populated_one(tmp_path, populated) -> None:
    """A payload whose KEYS depend on the data is a contract nobody can rely on.

    `embedding` was added to the populated branch and not to the empty one, so a
    reader hit `KeyError` instead of reading `None` whenever the store had
    nothing to show: an empty state dir, or a backend pointed at a directory
    written by the other backend.

    Comparing key SETS rather than listing them: a field added to one branch and
    forgotten in the other fails here without anyone updating this test.
    """
    from dashboard.backend import reads

    state, _ = populated
    empty = reads.topology(tmp_path / "nothing-here")
    full = reads.topology(state)

    assert set(empty) == set(full), (
        f"payload keys differ by data: only-empty={set(empty) - set(full)}, "
        f"only-populated={set(full) - set(empty)}"
    )
    assert empty["version"] == 0
    assert empty["embedding"] is None
    assert empty["agents"] == {} and empty["nodes"] == []


def test_the_suite_does_not_inherit_a_store_backend_from_the_shell() -> None:
    """The isolation `tests/conftest.py` installs, asserted rather than assumed.

    Without it, `CLE_STORE=sqlite pytest` turned six dashboard tests red: they
    build a `FileStore` explicitly, and `reads.topology` resolved a SqliteStore
    from the ambient variable over the same directory.
    """
    import os

    for name in ("CLE_STORE", "CLE_EMBEDDER", "CLE_VECTOR_CACHE"):
        assert name not in os.environ, (
            f"{name} leaked into the suite; assertions now depend on the shell "
            "that launched pytest"
        )

    # `CLE_FORCE_REAL_MODEL` is the one that fails intermittently rather than
    # loudly: set, the fingerprinter raises instead of falling back to its
    # offline hash, and which tests notice depends on collection order. It comes
    # back if anything imports a module that calls `load_dotenv()` at import
    # scope, which `examples/bigquery/bqconfig.py` does. Asserted here so that
    # reappearing is a named failure instead of a flaky suite.
    assert "CLE_FORCE_REAL_MODEL" not in os.environ, (
        "CLE_FORCE_REAL_MODEL is set inside the suite. Something re-read `.env` "
        "after tests/conftest.py cleared it; the fingerprinter will now raise "
        "instead of falling back, and the failures will look unrelated."
    )
