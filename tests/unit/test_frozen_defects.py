"""Known defects, pinned to their CURRENT behaviour.

Some defects are measured and deliberately not corrected, because correcting
them needs a decision nobody has made. Those still need a test, for the opposite
of the usual reason: **these go RED on the day the defect is fixed.** Without
them a fix lands silently and the documentation describing the defect becomes
wrong with nothing saying so.

Each test states what is frozen, why, and what to do when it fails.

`decline` writing no topology record is covered in
`tests/unit/test_cli_acceptance.py`, not duplicated here.
"""

from __future__ import annotations

import io

import pytest

from cle.oplog import OpLog
from cle.store.backends import InMemoryStore
from cle.store.commits import PreEvidence


# ── frozen defect: false_trigger_rate gates nothing ─────────────────────────

def test_a_ruinous_false_trigger_rate_still_births_a_candidate() -> None:
    """FROZEN. `false_trigger_rate` is computed, recorded, and gates nothing.

    `capture_rate` gates nothing either, and that is deliberate: replay produces
    `PreEvidence`, which by invariant 5 can never gate a promotion. But a birth
    is not a promotion, and nothing anywhere refuses a candidate whose trigger
    fires on almost everything. On the Stack Overflow corpus this rate measures
    0.580, and the candidate is born exactly as if it had measured 0.02.

    Not corrected because the threshold is undecided: no corpus has been used to
    calibrate one, and picking a number here would be a conclusion broader than
    its measurement.

    WHEN THIS FAILS: a birth threshold was introduced. Good. Update
    `docs/METRICS.md` and `docs/FINDINGS.md`, which both describe 0.580 as a
    measured defect left standing, and delete this test.
    """
    ruinous = PreEvidence(
        capture_rate=1.0, false_trigger_rate=0.99, historical_cost=4.0, window="30d"
    )
    # The type accepts it. Nothing in the model refuses it.
    assert ruinous.false_trigger_rate == 0.99

    from cle.lifecycle.topology import write_topology
    from cle.detect.clusters import HashedTokenEmbedder
    from cle.detect.embedders import embedding_config_for
    from tests.unit.test_runtime import _build_image
    import tempfile
    from pathlib import Path

    store = InMemoryStore()
    oplog = OpLog(io.StringIO())
    image = _build_image(store, oplog)
    topo = Path(tempfile.mkdtemp()) / "topology.yaml"

    ref = write_topology(
        backend=store, path=topo, agent="ruinous", state="candidate",
        image_hash=image.hash, cause={"pre_evidence": ruinous.model_dump()},
        oplog=oplog, actor="human:test",
        embedding=embedding_config_for(HashedTokenEmbedder()),
    )
    assert ref == "topology/v1", (
        "a candidate whose trigger fires on 99% of unrelated traffic was born "
        "without objection; if this now raises, a birth gate exists and this "
        "frozen defect is fixed"
    )


def test_the_evidence_gate_does_refuse_pre_evidence() -> None:
    """The negative, so the test above cannot be read as 'nothing is gated'.

    Invariant 5 IS enforced: replay numbers cannot be smuggled into a promotion.
    What is missing is a gate on birth, which is a different question.
    """
    from cle.lifecycle.tags import move_state_tag

    with pytest.raises(Exception):
        move_state_tag(
            backend=InMemoryStore(), agent="x", to_state="ephemeral",
            image_hash="0" * 64, evidence=PreEvidence(
                capture_rate=1.0, false_trigger_rate=0.0,
                historical_cost=1.0, window="30d",
            ),
            oplog=OpLog(io.StringIO()), actor="human:test",
        )


# ── frozen defect: `cle clean` is still rmtree ─────────────────────────────

def test_clean_with_yes_still_deletes_everything(tmp_path) -> None:
    """FROZEN. The confirmation is a prompt, not a safety net.

    `cle clean` remains `shutil.rmtree` on a gitignored directory holding the
    only copy of the oplog, the store and the topology history. The confirmation
    addresses the operator who mistyped a path; it does nothing for the operator
    who confirms, or for `--yes` in a script. There is no backup, no trash, no
    undo.

    Not corrected because the alternative (move to a timestamped `.cle.bak`,
    or refuse without an explicit `--force`) is a design decision about the
    state directory's lifecycle, not a cleanup.

    WHEN THIS FAILS: `clean` stopped being destructive. Update `README.md`,
    which documents it as `Reset the state directory`, and `docs/CAPABILITIES`.
    """
    from typer.testing import CliRunner

    from cle.cli.main import app

    state = tmp_path / "scratch"
    state.mkdir()
    (state / "log.jsonl").write_text('{"op":"build"}\n')
    (state / "topology.yaml").write_text("agents: {}\n")
    (state / "store").mkdir()
    (state / "store" / "abc").write_bytes(b"the only copy")

    result = CliRunner().invoke(app, ["clean", "--state-dir", str(state), "--yes"])

    assert result.exit_code == 0, result.output
    assert not state.exists(), "the directory survived, so `clean` is no longer rmtree"


def test_clean_without_yes_asks_and_a_refusal_keeps_everything(tmp_path) -> None:
    """The confirmation, pinned so it cannot quietly disappear.

    This is the half that IS addressed. Losing it restores a bare `rmtree` on
    the only copy of a state directory git cannot bring back.
    """
    from typer.testing import CliRunner

    from cle.cli.main import app

    state = tmp_path / "scratch"
    state.mkdir()
    (state / "log.jsonl").write_text("{}\n")

    result = CliRunner().invoke(
        app, ["clean", "--state-dir", str(state)], input="n\n"
    )

    assert result.exit_code == 1
    assert "Delete it?" in result.output
    assert state.exists() and (state / "log.jsonl").exists()
