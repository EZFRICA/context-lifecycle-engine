"""Level 2 end to end, through the CLI: births write facets, `cle population` reads them.

SCOPE: bucket 2 (stub-as-a-tool). The builds run on `--embedder stub` and a stub
fingerprinter, and the population embeds facets in the stub space. The claims -
a facet at every true birth, none at a rebuild, a report that names only what
three instances produced and quotes no facet - hold in any space. Bucket 1 for
the two that are refused before anything is embedded.

Three state dirs stand for three users. Each builds the same three agents from
the same history, so each agent's facet is identical across the three: a group
of three users, exactly at the floor.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cle.cli.main import app
from cle.lifecycle.topology import current_agents
from cle.store.backends import open_store
from tests.unit.test_refusals_bite import _said  # plain text, whatever Rich decides

ROOT = Path(__file__).resolve().parent.parent.parent
HISTORY = ROOT / "examples" / "prompt_history_adversarial.jsonl"
AGENTS = ("status_report", "weekly_recap", "standup_digest")


def _build(runner: CliRunner, state: Path, agent: str, specs: Path):
    return runner.invoke(app, [
        "build", str(specs / f"{agent}_agent.yaml"), "--history", str(HISTORY),
        "--replay-window", "40d", "--components", str(ROOT / "examples" / "components"),
        "--model-id", "stub-model-1", "--state-dir", str(state),
    ])


@pytest.fixture(scope="module")
def specs(tmp_path_factory) -> Path:
    """The era-A agent specs, generated here by `examples/make_fixture.py`.

    Not read from `examples/`: the agent YAMLs there are gitignored and
    regenerated on every demo run, so a clean clone - and CI - has none.
    """
    import make_fixture

    out = tmp_path_factory.mktemp("specs") / "generated"  # absent: main() creates it
    make_fixture.main(out)
    return out


@pytest.fixture(scope="module")
def instances(tmp_path_factory, specs) -> list[Path]:
    runner = CliRunner()
    dirs = []
    for user in ("u1", "u2", "u3"):
        state = tmp_path_factory.mktemp(user)
        for agent in AGENTS:
            result = _build(runner, state, agent, specs)
            assert result.exit_code == 0, result.output
            assert "facet               present" in result.output, result.output
        dirs.append(state)
    return dirs


def test_every_true_birth_carries_a_facet(instances) -> None:
    for state in instances:
        agents = current_agents(open_store(state))
        assert {a: e["facet_status"] for a, e in agents.items()} == dict.fromkeys(AGENTS, "present")


def test_a_rebuild_does_not_regenerate_the_facet(instances, specs) -> None:
    state = instances[0]
    before = current_agents(open_store(state))["weekly_recap"]["facet"]
    result = _build(CliRunner(), state, "weekly_recap", specs)
    assert result.exit_code == 0, result.output
    assert "facet " not in result.output, "a rebuild must not report a new facet"
    assert current_agents(open_store(state))["weekly_recap"]["facet"] == before


def test_population_groups_the_same_agent_across_three_users(instances, tmp_path) -> None:
    out = tmp_path / "population"
    result = CliRunner().invoke(app, ["population", *map(str, instances),
                                      "--threshold", "0.99", "--out", str(out)])
    assert result.exit_code == 0, result.output

    report = json.loads((out / "report.json").read_text())
    assert (report["instances"], report["agents"]) == (3, 9)
    # Two agents may share a facet: `status_report` and `weekly_recap` compete
    # for one intent, and the stub writes the same sentence for the same
    # vocabulary. At 0.99 only identical facets group, so the expected count is
    # the number of DISTINCT facets, not the number of agents.
    distinct = {e["facet"]["text"] for e in current_agents(open_store(instances[0])).values()}
    assert report["groups"] == len(distinct) and report["named"] == len(distinct)
    assert all(g["users"] == 3 and g["size"] % 3 == 0 and g["name"]
               for g in report["group_summaries"])

    raw = (out / "report.json").read_text()
    for state in instances:
        for entry in current_agents(open_store(state)).values():
            assert entry["facet"]["text"] not in raw, "a report must never quote a facet"

    line = json.loads((out / "log.jsonl").read_text().splitlines()[-1])
    assert line["op"] == "population_report" and line["groups"] == len(distinct)


def test_two_users_are_below_the_floor_and_name_nothing(instances, tmp_path) -> None:
    out = tmp_path / "two"
    result = CliRunner().invoke(app, ["population", *map(str, instances[:2]),
                                      "--threshold", "0.99", "--out", str(out)])
    assert result.exit_code == 0, result.output
    report = json.loads((out / "report.json").read_text())
    assert report["named"] == 0
    assert all(g["name"] is None for g in report["group_summaries"])


def test_population_refuses_a_directory_with_nothing_born_in_it(instances, tmp_path) -> None:
    result = CliRunner().invoke(app, ["population", str(instances[0]), str(tmp_path),
                                      "--out", str(tmp_path / "out")])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "population refused" in result.output + (result.stderr or "")


@pytest.mark.parametrize("exists", [False, True], ids=["missing", "empty"])
def test_population_never_creates_what_it_was_asked_to_read(tmp_path, exists) -> None:
    """A read that creates is a write: opening a store makes its directory.

    Before the reader asked first, both cases were refused AND left
    `<dir>/store/objects` behind - in a path that was someone else's instance.
    """
    target = tmp_path / "never_born"
    if exists:
        target.mkdir()
    result = CliRunner().invoke(app, ["population", str(target), "--out", str(tmp_path / "out")])
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    assert "population refused" in result.output + (result.stderr or "")
    assert target.exists() is exists
    assert not exists or not any(target.iterdir()), list(target.iterdir())


def test_population_refuses_an_unknown_namer(instances, tmp_path) -> None:
    result = CliRunner().invoke(app, ["population", str(instances[0]), "--namer", "bogus",
                                      "--out", str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "--namer must be one of" in _said(result)
