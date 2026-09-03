"""`$CLE_VECTOR_CACHE` is a PATH override, never a SPACE override.

The variable lets a corpus larger than the committed fixtures run through the
CLI without paying to re-embed on every build. Its danger is silent:
`CachedEmbedder` reads its `embedder_id` FROM THE FILE, so pointing the variable
at a cache built in another space swaps the geometry underneath a history born
elsewhere. Centroids do not survive that, and nothing about the run looks
different — same command, same exit code, different vector space.

Two things hold the line, and only one of them is designed to:

  * an UNCALIBRATED foreign id is stopped by `UnknownCalibrationError`, but only
    INCIDENTALLY, because `CALIBRATION_PROVENANCE` happens to hold two entries.
    Adding a third would remove that stop.
  * a CALIBRATED foreign id is stopped by `EmbeddingConfigMismatchError` at the
    topology write. That is the guard that has to survive.

So the load-bearing case is `test_calibrated_foreign_space_still_refused`, which
simulates the future in which somebody adds the calibration entry.
"""

from __future__ import annotations

import io
import json

import pytest

from cle.batch_guard import UnnormalisedVectorError
from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.embedders import (
    CALIBRATION_PROVENANCE,
    CachedEmbedder,
    UnknownCalibrationError,
    embedding_config_for,
)
from cle.lifecycle.topology import EmbeddingConfigMismatchError, write_topology
from cle.oplog import OpLog
from cle.store.backends import InMemoryStore
from cle.store.commits import PreEvidence

from tests.unit.test_runtime import _build_image

ALIEN_ID = "google:gemini-embedding-001:768"


def _cache_file(tmp_path, embedder_id: str, vectors: dict[str, list[float]]):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps(
        {"embedder_id": embedder_id, "dim": 768, "count": len(vectors), "vectors": vectors}
    ))
    return path


def _unit(seed: float) -> list[float]:
    """A unit vector, so the norm guard is not what fails these tests."""
    values = [0.0] * 768
    values[int(seed) % 768] = 1.0
    return values


def test_id_comes_from_the_file_not_from_the_variable(tmp_path, monkeypatch):
    """The override moves WHERE vectors are read, never WHAT SPACE they claim."""
    path = _cache_file(tmp_path, ALIEN_ID, {"a" * 64: _unit(1)})
    monkeypatch.setenv("CLE_VECTOR_CACHE", str(path))

    embedder = CachedEmbedder.from_file(path)
    assert embedder.embedder_id == ALIEN_ID, (
        "the cache file declares the space; if this ever reads the env var or a "
        "default instead, a foreign cache would masquerade as the CLE's own"
    )


def test_uncalibrated_foreign_space_refused(tmp_path):
    """The incidental stop, pinned so its disappearance is visible."""
    path = _cache_file(tmp_path, ALIEN_ID, {"a" * 64: _unit(1)})
    assert ALIEN_ID not in CALIBRATION_PROVENANCE, (
        "if this id gained a calibration entry, the only remaining guard is the "
        "topology mismatch below — which is why that test exists"
    )
    with pytest.raises(UnknownCalibrationError):
        embedding_config_for(CachedEmbedder.from_file(path))


def test_calibrated_foreign_space_still_refused(tmp_path, monkeypatch):
    """THE load-bearing case: a calibrated foreign space must not slip in.

    Simulates the future where `gemini-embedding-001` is added to
    `CALIBRATION_PROVENANCE`. `UnknownCalibrationError` stops firing; the write
    must still be refused, because the history was born in another space.
    """
    monkeypatch.setitem(CALIBRATION_PROVENANCE, ALIEN_ID, "simulated future entry")

    store = InMemoryStore()
    oplog = OpLog(io.StringIO())
    image = _build_image(store, oplog)
    topo = tmp_path / "topology.yaml"

    born_in = embedding_config_for(HashedTokenEmbedder())
    write_topology(
        backend=store, path=topo, agent="recap", state="trial", image_hash=image.hash,
        cause={"pre_evidence": PreEvidence(
            capture_rate=0.9, false_trigger_rate=0.02, historical_cost=4.0, window="30d",
        ).model_dump()},
        oplog=oplog, actor="human:test", embedding=born_in,
    )

    alien_cache = _cache_file(tmp_path, ALIEN_ID, {"a" * 64: _unit(1)})
    monkeypatch.setenv("CLE_VECTOR_CACHE", str(alien_cache))
    alien = embedding_config_for(CachedEmbedder.from_file(alien_cache))
    assert alien.embedder_id != born_in.embedder_id

    with pytest.raises(EmbeddingConfigMismatchError):
        write_topology(
            backend=store, path=topo, agent="recap", state="ephemeral",
            image_hash=image.hash, cause={"persistence": "probe"}, oplog=oplog,
            actor="human:test", embedding=alien,
        )


def test_override_path_still_checked_for_norm(tmp_path):
    """The override does not bypass the norm check on cache loads.

    A cache regenerated through BigQuery's `ML.GENERATE_EMBEDDING` comes back at
    0.58-0.60, which would quietly stop `cosine` from being a cosine.
    """
    path = _cache_file(tmp_path, ALIEN_ID, {"a" * 64: [0.5] * 768})
    with pytest.raises(UnnormalisedVectorError):
        CachedEmbedder.from_file(path)
