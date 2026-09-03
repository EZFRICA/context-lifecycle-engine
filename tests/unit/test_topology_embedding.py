"""The embedding configuration recorded in topology.yaml.

SCOPE — bucket 1 (embedder-agnostic): the assertions are about what the
topology RECORDS, not about any vector space's behaviour. The stub embedder
appears only as a thing with an `embedder_id`.

CLE need: two instances on the same embedder at 0.775 and at 0.72 do not birth
the same agents from the same usage. A population-level report that aggregated
their topologies would measure its own instrumentation rather than its
population — the v1 failure mode transposed. So the configuration is an
AGGREGATION KEY: recorded at topology scope, written only by the engine.
"""

import io

import pytest
import yaml

from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.embedders import (
    CALIBRATION_PROVENANCE,
    UnknownCalibrationError,
    embedding_config_for,
)
from cle.lifecycle.topology import MissingEmbeddingConfigError, latest_version, write_topology
from cle.oplog import OpLog
from cle.store.backends import InMemoryStore
from cle.store.commits import Evidence, Image, PreEvidence, TriggerSpec


def _image() -> Image:
    return Image(
        source_hash="0" * 64, resolved_refs={}, assembled_prompt="p",
        trigger=TriggerSpec(centroid=(1.0, 0.0), embedder_id="stub:hashed64"),
        model_fingerprint="f" * 64,
        pre_evidence=PreEvidence(capture_rate=1.0, false_trigger_rate=0.0,
                                 historical_cost=3.0, window="30d"),
        probe_set=("p",), probe_output_hashes=("h",),
    )


def _seeded_store() -> tuple[InMemoryStore, Image]:
    store, image = InMemoryStore(), _image()
    store.put(image.hash, image.canonical_bytes())
    return store, image


def _write(store, image, tmp_path, *, state="trial", cause=None, embedding=None):
    return write_topology(
        backend=store, path=tmp_path / "topology.yaml", agent="recap", state=state,
        image_hash=image.hash,
        cause=cause or {"pre_evidence": image.pre_evidence.model_dump()},
        oplog=OpLog(io.StringIO()), actor="human:t", embedding=embedding,
    )


# ── the config is derived from the embedder, never hand-written ─────────────

def test_config_is_derived_from_the_embedder_in_use() -> None:
    config = embedding_config_for(HashedTokenEmbedder())
    assert config.embedder_id == "stub:hashed64"
    assert config.cluster_threshold == 0.6          # the space's own threshold
    assert config.calibration                        # provenance is never blank


def test_an_embedder_without_recorded_calibration_raises() -> None:
    # No "unknown" catch-all: a configuration nobody can account for would be
    # aggregated as if it were accounted for.
    class Unswept:
        embedder_id = "someone:new-model:512"

    with pytest.raises(UnknownCalibrationError):
        embedding_config_for(Unswept())


def test_an_object_that_is_not_an_embedder_raises() -> None:
    class Nameless:
        pass

    with pytest.raises(UnknownCalibrationError):
        embedding_config_for(Nameless())


def test_every_shipped_embedder_id_has_a_calibration_recorded() -> None:
    from cle.detect.clusters import CLUSTER_THRESHOLD_BY_EMBEDDER

    missing = sorted(set(CLUSTER_THRESHOLD_BY_EMBEDDER) - set(CALIBRATION_PROVENANCE))
    assert not missing, (
        f"embedders with a tuned threshold but no calibration provenance: {missing}. "
        "A threshold whose origin nobody can name is a guess, not a configuration."
    )


# ── topology scope, and inheritance ─────────────────────────────────────────

def test_the_first_write_records_the_config_at_topology_scope(tmp_path) -> None:
    store, image = _seeded_store()
    _write(store, image, tmp_path, embedding=embedding_config_for(HashedTokenEmbedder()))
    _version, record = latest_version(store)
    assert record["embedding"]["embedder_id"] == "stub:hashed64"
    # Topology scope, NOT per agent: the key describes the whole history.
    assert "embedding" not in record["agents"]["recap"]


def test_later_writes_inherit_it_rather_than_re_deriving(tmp_path) -> None:
    store, image = _seeded_store()
    _write(store, image, tmp_path, embedding=embedding_config_for(HashedTokenEmbedder()))
    _write(store, image, tmp_path, state="ephemeral",
           cause={"evidence": Evidence(cost_ratio=0.6, occurrences=4,
                                       closure_tags=("success",)).model_dump()})
    _version, record = latest_version(store)
    assert record["version"] == 2
    assert record["embedding"]["embedder_id"] == "stub:hashed64"


def test_a_first_write_without_a_config_raises(tmp_path) -> None:
    # No silent fallback: a history with no recorded vector space is comparable
    # with nothing, and must never enter an aggregate pretending otherwise.
    store, image = _seeded_store()
    with pytest.raises(MissingEmbeddingConfigError):
        _write(store, image, tmp_path)


def test_the_visible_yaml_carries_it_too(tmp_path) -> None:
    # The audit surface humans read, not only the store record.
    store, image = _seeded_store()
    _write(store, image, tmp_path, embedding=embedding_config_for(HashedTokenEmbedder()))
    document = yaml.safe_load((tmp_path / "topology.yaml").read_text())
    assert document["embedding"]["embedder_id"] == "stub:hashed64"
    assert document["embedding"]["cluster_threshold"] == 0.6
