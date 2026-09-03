"""The live revalidation path reports drift but must never write it.

SCOPE: bucket 1 (embedder-agnostic). The topology is written under the stub;
nothing here asserts anything about a vector space.

CLE need. A served model is not deterministic at temperature 0: probing the same
frozen probe set twice against an UNCHANGED substrate produces different
fingerprints. So a live revalidation reports drift every time, and writing that
drift would put a `Persistence` (one of the three type-separated standards of
proof) into the single channel a population level reads, asserting a substrate
change that did not happen. A fabricated proof is worse than a missing one.

The guard lives in the CLI command, not in the library revalidator, and it was
the one branch with no coverage of any kind. It cannot be reached with a
`stub-*` model id, which is what the rest of the suite uses, and reaching it for
real costs a live call on every run.

So `LiveModelFingerprinter` is substituted with a stand-in that reports drift
deterministically. That exercises the exact branch, offline and free, and the
substitution is the point: what is under test is the CLI's decision after drift
is reported, not the model that reports it.
"""

from __future__ import annotations

import io

import pytest
import yaml
from typer.testing import CliRunner

from cle.cli.main import app
from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.embedders import embedding_config_for
from cle.lifecycle.topology import write_topology
from cle.oplog import OpLog
from cle.store.backends import FileStore
from cle.store.commits import Evidence, PreEvidence

from tests.unit.test_runtime import _build_image


class _AlwaysDrifts:
    """Stands in for `LiveModelFingerprinter`: every probe comes back different.

    This is what a real served model does at temperature 0, which is the whole
    reason the guard exists.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._call = 0

    def outputs(self, probes):
        self._call += 1
        return tuple(f"drifted-{self._call}-{index}" for index, _ in enumerate(probes))


@pytest.fixture()
def promoted(tmp_path):
    """An agent sitting at `ephemeral`, which is what auto-demotion acts on."""
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
    return state, topo


def _versions(topo):
    return yaml.safe_load(topo.read_text())["version"]


def test_the_live_path_reports_drift_and_writes_nothing(promoted, monkeypatch) -> None:
    """`--model-id current` on a drifting substrate: reported, never recorded."""
    import cle.build.fingerprinter as fingerprinter

    monkeypatch.setattr(fingerprinter, "LiveModelFingerprinter", _AlwaysDrifts)

    state, topo = promoted
    before_version = _versions(topo)
    before_bytes = topo.read_bytes()

    result = CliRunner().invoke(
        app, ["revalidate", "recap", "--model-id", "current", "--state-dir", str(state)]
    )

    assert result.exit_code == 0, result.output
    assert "DRIFT:" in result.output, "the drift must still be reported to the operator"
    assert "NOT written to topology" in result.output

    assert topo.read_bytes() == before_bytes, (
        "the live path wrote a Persistence into topology.yaml; that asserts a "
        "substrate change the non-determinism of the model cannot support"
    )
    assert _versions(topo) == before_version
    assert yaml.safe_load(topo.read_text())["agents"]["recap"]["state"] == "ephemeral", (
        "the live path demoted the agent; drift under a non-deterministic model "
        "is not evidence of substrate change"
    )


def test_the_stub_path_does_demote_and_write(promoted) -> None:
    """The negative, so the guard above cannot be read as 'drift never demotes'.

    A `stub-*` model id is deterministic by construction, so drift under it IS
    evidence: the agent demotes and the topology records the `Persistence`. If
    this ever stops happening, the guard above has been over-applied.
    """
    state, topo = promoted
    before_version = _versions(topo)

    result = CliRunner().invoke(
        app,
        ["revalidate", "recap", "--model-id", "drifted-model-2", "--state-dir", str(state)],
    )

    assert result.exit_code == 0, result.output
    assert "DRIFT:" in result.output
    assert "auto-demoted" in result.output

    record = yaml.safe_load(topo.read_text())
    assert _versions(topo) == before_version + 1
    assert record["agents"]["recap"]["state"] == "trial"
    assert "persistence" in record["agents"]["recap"]["cause"]
