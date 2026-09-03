"""End-to-end acceptance: the CLI itself, on the independent GDG fixture.

SCOPE — bucket 2 (stub-as-a-tool): runs on `--embedder stub`, the space every
existing topology was produced in. No assertion here is about the geometry.

CLE need — the gap this closes. Without this file **the whole CLI is dead
code for the suite**: all 10 commands and every helper but `_store` are executed
by no test. The documented architecture says every write goes through the CLI,
so the suite covered the bricks writes are made of and no write PATH. The
question "does the system behave as intended end to end" therefore had no
mechanical answer. This file is that answer.

It drives the CLI through `CliRunner` (the Typer app, not the libraries beneath
it) on `prompt_history_gdg.jsonl` — one of the two fixture generators declared
independent of the detector — into a throwaway state dir. It never touches
`.cle`, and it never invokes `cle clean`, which is `shutil.rmtree` without
confirmation on a gitignored directory that is the only source a population
level reads.

TWO TESTS BELOW FREEZE A KNOWN DEFECT ON PURPOSE. They assert what the commands
DO, not what they should do, and say so in their names and bodies. A test
asserting the intended behaviour would fail today and be disabled within a week;
a test asserting the real behaviour makes the defect visible and fails loudly on
the day it is fixed — which is when someone should be looking.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from cle.cli.main import app
from cle.detect.clusters import IntentClusterer
from cle.detect.embedders import open_embedder
from cle.detect.episodes import DetectorConfig, Message, segment

ROOT = Path(__file__).resolve().parent.parent.parent
GDG_HISTORY = ROOT / "examples" / "prompt_history_gdg.jsonl"

#: `cle build` defaults to `--model-id current`, which is the LIVE model: a bare
#: `cle build` spends money, and so did the first run of this file. Every build
#: below pins the deterministic offline fingerprinter instead. Found by this
#: file, and worth knowing: the paid path is the default.
OFFLINE_MODEL = ("--model-id", "stub-model-1")


def _run(runner: CliRunner, state: Path, *argv: str):
    """Invoke the CLI. `--state-dir` is per-command, so it follows the subcommand."""
    result = runner.invoke(app, [*argv, "--state-dir", str(state)])
    return result


@pytest.fixture(scope="module")
def gdg_history(tmp_path_factory) -> Path:
    """A TRIMMED slice of the independent fixture.

    The full corpus is 516 texts / 246 episodes, and replaying it took ~5.5s per
    command — the rest of the suite runs under 10ms per test, and a slow test is
    one people learn to skip. The slice keeps the corpus and its structure and
    only shortens it; nothing here asserts a detection quality figure, so the
    length is not load-bearing. Measure A (docs/METRICS.md) is where the full
    corpus matters.
    """
    if not GDG_HISTORY.exists():
        pytest.skip("GDG fixture absent; run examples/make_gdg_fixture.py")
    lines = GDG_HISTORY.read_text().splitlines()[:90]
    path = tmp_path_factory.mktemp("hist") / "gdg_slice.jsonl"
    path.write_text("\n".join(lines) + "\n")
    return path


@pytest.fixture(scope="module")
def gdg_spec(tmp_path_factory, gdg_history) -> Path:
    """An agent spec whose centroid is DERIVED from the independent fixture.

    Not `examples/*_agent.yaml`: those come from `make_fixture.py`, which imports
    the detector and treats "distinct vocabularies -> distinct centroids" as a
    design goal (era A). Deriving the centroid here from GDG data keeps the
    acceptance path on the independent corpus.
    """
    records = [json.loads(line) for line in gdg_history.read_text().splitlines()]
    config = DetectorConfig()
    messages = [
        Message(**{k: r.get(k) for k in
                   ("text", "ts", "thread_id", "user_id", "requires_tool", "tool_result")})
        for r in records
    ]
    episodes = segment(messages, config)
    embedder = open_embedder("stub")
    clusterer = IntentClusterer(embedder, config)
    counts: dict[int, int] = {}
    for episode in episodes:
        counts[clusterer.assign(episode)] = counts.get(clusterer.assign(episode), 0) + 1
    biggest = max(counts, key=counts.get)

    path = tmp_path_factory.mktemp("spec") / "gdg_agent.yaml"
    path.write_text(yaml.safe_dump({
        "name": "gdg_agent",
        "detected_from": {"signal": "recurrence", "occurrences": counts[biggest]},
        "components": [],
        "trigger": {
            "centroid": [round(v, 6) for v in clusterer.centroids[biggest]],
            # Provenance is mandatory: a centroid is only meaningful in
            # the space that produced it, and replay now refuses a mismatch.
            "embedder_id": embedder.embedder_id,
        },
    }, sort_keys=False))
    return path


@pytest.fixture(autouse=True)
def _isolate_cli_env(monkeypatch: pytest.MonkeyPatch):
    """Undo the CLI callback's process-wide env writes between tests.

    FOUND BY THIS FILE, on its first run. `cli()` sets `os.environ["CLE_STORE"]`
    and `os.environ["CLE_EMBEDDER"]` deliberately, so that the dashboard
    SUBPROCESS agrees with the CLI on backend and vector space. In a shell that
    is per-process and correct. In-process it is sticky: one `--embedder cached`
    invocation silently governed every later one, and a build that should have
    written a topology was refused by the space gate instead.

    Nothing in `cle/` resets it, so any long-lived in-process host — a test
    runner, a notebook, an embedding application — inherits the last invocation's
    choice. Recorded here rather than fixed, because whether
    the callback should scope or reset is a design decision.
    """
    import os

    saved = {k: os.environ.get(k) for k in ("CLE_STORE", "CLE_EMBEDDER")}
    for key in saved:
        os.environ.pop(key, None)
    yield
    # Restore explicitly: `monkeypatch` cannot undo a variable the CODE set
    # during the test, and that is precisely what the callback does. Without
    # this, one `--embedder cached` invocation here leaked into OTHER test
    # modules and failed them — the leak crosses files, not just tests.
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def state(tmp_path) -> Path:
    return tmp_path / "cle"


def _topology(state: Path) -> dict:
    return yaml.safe_load((state / "topology.yaml").read_text())


# ── birth ───────────────────────────────────────────────────────────────────

def test_build_births_a_candidate_and_records_what_caused_it(gdg_spec, gdg_history, state) -> None:
    runner = CliRunner()
    result = _run(runner, state, "build", str(gdg_spec),
                  "--replay-window", "40d", "--history", str(gdg_history), *OFFLINE_MODEL)
    assert result.exit_code == 0, result.output
    assert "two_hashes_distinct True" in result.output, result.output

    document = _topology(state)
    entry = document["agents"]["gdg_agent"]
    assert entry["state"] == "candidate"
    # Birth rides replay, never lived evidence — the ladder's whole point.
    assert set(entry["cause"]) == {"pre_evidence"}
    # The aggregation key: without it a topology compares to nothing.
    assert document["embedding"]["embedder_id"] == "stub:hashed64"
    assert document["embedding"]["cluster_threshold"] == 0.6


# ── promotion ───────────────────────────────────────────────────────────────

def test_promotion_to_ephemeral_requires_and_records_lived_evidence(gdg_spec, gdg_history, state) -> None:
    runner = CliRunner()
    _run(runner, state, "build", str(gdg_spec),
         "--replay-window", "40d", "--history", str(gdg_history), *OFFLINE_MODEL)

    up = _run(runner, state, "tag", "gdg_agent", "trial")
    assert up.exit_code == 0, up.output
    assert _topology(state)["agents"]["gdg_agent"]["state"] == "trial"

    lived = _run(runner, state, "tag", "gdg_agent", "ephemeral",
                 "--cost-ratio", "0.6", "--occurrences", "4", "--closures", "success")
    assert lived.exit_code == 0, lived.output
    # The shadow engine judges the same evidence and says so; it writes no ref.
    assert "engine:shadow would:" in lived.output, lived.output

    entry = _topology(state)["agents"]["gdg_agent"]
    assert entry["state"] == "ephemeral"
    assert set(entry["cause"]) == {"evidence"}


def test_promotion_to_ephemeral_without_evidence_is_refused(gdg_spec, gdg_history, state) -> None:
    runner = CliRunner()
    _run(runner, state, "build", str(gdg_spec),
         "--replay-window", "40d", "--history", str(gdg_history), *OFFLINE_MODEL)
    _run(runner, state, "tag", "gdg_agent", "trial")
    # No --cost-ratio / --occurrences: replay proof must not stand in for lived
    # proof. This is the one thing the ladder exists to prevent.
    refused = _run(runner, state, "tag", "gdg_agent", "ephemeral")
    assert refused.exit_code != 0, refused.output


# ── descent: FREEZES A KNOWN DEFECT ─────────────────────────────────────────

def test_descent_to_trial_records_its_reason_not_the_birth_evidence(
    gdg_spec, gdg_history, state
) -> None:
    """The direction of a tag move decides which cause is recorded.

    `cle/cli/main.py` tested the DESTINATION (`to_state in ("trial",
    "candidate")`), so a descent into either state loaded the image's birth
    `pre_evidence` and recorded THAT as the cause — the demotion reached the
    topology channel labelled "caused by the replay proof of its own birth",
    and the closed-vocabulary reason was silently dropped. A false field, not a
    missing one.

    It now tests the DIRECTION. `from_state` is read from `current_agents`
    before the write, so direction is computable there and does not depend on
    deriving it from the chain diff.
    """
    runner = CliRunner()
    _run(runner, state, "build", str(gdg_spec),
         "--replay-window", "40d", "--history", str(gdg_history), *OFFLINE_MODEL)
    _run(runner, state, "tag", "gdg_agent", "trial")
    _run(runner, state, "tag", "gdg_agent", "ephemeral",
         "--cost-ratio", "0.6", "--occurrences", "4", "--closures", "success")

    down = _run(runner, state, "tag", "gdg_agent", "trial",
                "--reason", "cost_regression", "--note", "local prose, must not travel")
    assert down.exit_code == 0, down.output

    entry = _topology(state)["agents"]["gdg_agent"]
    assert entry["state"] == "trial"
    assert entry["cause"] == {"reason": "cost_regression"}
    # The free-text note still never crosses into topology.
    assert "local prose" not in (state / "topology.yaml").read_text()


def test_an_upward_move_to_trial_still_rides_birth_evidence(
    gdg_spec, gdg_history, state
) -> None:
    # The other half of the direction fix: promotion into `trial` must still
    # carry the replay proof. Correcting the descent must not break the ascent.
    runner = CliRunner()
    _run(runner, state, "build", str(gdg_spec),
         "--replay-window", "40d", "--history", str(gdg_history), *OFFLINE_MODEL)
    up = _run(runner, state, "tag", "gdg_agent", "trial")
    assert up.exit_code == 0, up.output
    assert set(_topology(state)["agents"]["gdg_agent"]["cause"]) == {"pre_evidence"}


def test_descent_to_archived_does_record_the_closed_vocabulary_reason(
    gdg_spec, gdg_history, state
) -> None:
    # The one descent that works: `archived` is not in the destination list that
    # triggers the pre_evidence load, so the reason survives. Kept alongside the
    # test above so the defect reads as a direction bug, not a reason bug.
    runner = CliRunner()
    _run(runner, state, "build", str(gdg_spec),
         "--replay-window", "40d", "--history", str(gdg_history), *OFFLINE_MODEL)
    _run(runner, state, "tag", "gdg_agent", "trial")
    gone = _run(runner, state, "tag", "gdg_agent", "archived", "--reason", "cost_regression")
    assert gone.exit_code == 0, gone.output
    entry = _topology(state)["agents"]["gdg_agent"]
    assert entry["cause"]["reason"] == "cost_regression"


# ── decline: FREEZES A KNOWN DEFECT ─────────────────────────────────────────

def test_decline_still_writes_no_topology_record_and_this_is_open(
    gdg_spec, gdg_history, state
) -> None:
    """A frozen defect, deliberately not corrected.

    `decline` moves no tag by design, so it writes no topology version: a human
    refusal — the clearest signal a population report could carry — exists only
    in the oplog, which level 2 never reads. Half the closed vocabulary
    (`engine_disagrees`, `defer`) can never reach the channel it was built for.

    Why it is frozen rather than fixed: a consumer of the
    chain diff. `dashboard/backend/reads.py:topology_diff` classifies every
    entry-level difference as added / removed / retagged, so a decline record
    carrying an UNCHANGED state would surface as `retagged` with
    `from_state == to_state` — a state change that did not happen, asserted in
    the audit surface. Choosing between "a record with a `declined` marker every
    diff consumer must learn to ignore" and "a distinct record kind in the
    chain" is a design decision, and it was escalated rather than taken.

    Invert this test when that decision lands.
    """
    runner = CliRunner()
    _run(runner, state, "build", str(gdg_spec),
         "--replay-window", "40d", "--history", str(gdg_history), *OFFLINE_MODEL)
    before = _topology(state)["version"]

    refused = _run(runner, state, "decline", "gdg_agent", "--reason", "engine_disagrees")
    assert refused.exit_code == 0, refused.output

    # CURRENT behaviour, not desired: the topology did not advance at all.
    assert _topology(state)["version"] == before
    assert "engine_disagrees" not in (state / "topology.yaml").read_text()
    # It IS in the local channel.
    assert "engine_disagrees" in (state / "log.jsonl").read_text()


# ── the space contract, through the CLI ─────────────────────────────────────

def test_a_stub_spec_under_a_different_embedder_is_refused(gdg_spec, gdg_history, state) -> None:
    # The vector contract, exercised through the command rather than the library:
    # the centroid is stub-space, the embedder is not, and the build must refuse
    # instead of returning a plausible cross-space number.
    runner = CliRunner()
    result = runner.invoke(app, [
        "--embedder", "cached", "build", str(gdg_spec),
        "--replay-window", "40d", "--history", str(gdg_history), *OFFLINE_MODEL,
        "--state-dir", str(state),
    ])
    assert result.exit_code != 0
    assert "space that produced it" in result.output, result.output


def test_the_cli_never_writes_to_the_repository_state_dir(gdg_spec, gdg_history, state) -> None:
    # The failure mode that contaminated `.cle` twice: `--state-dir` is a
    # PER-COMMAND option, and CLE_STATE_DIR is not read by the CLI at all.
    runner = CliRunner()
    _run(runner, state, "build", str(gdg_spec),
         "--replay-window", "40d", "--history", str(gdg_history), *OFFLINE_MODEL)
    assert (state / "topology.yaml").exists()


def test_the_console_entry_point_is_the_same_app() -> None:
    # CliRunner drives the Typer app in-process. This one call proves the
    # installed console script reaches it, so the tests above are not exercising
    # a parallel universe.
    out = subprocess.run(
        [sys.executable, "-m", "cle.cli.main", "--help"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert out.returncode == 0
    for command in ("build", "tag", "decline", "revalidate", "log"):
        assert command in out.stdout
