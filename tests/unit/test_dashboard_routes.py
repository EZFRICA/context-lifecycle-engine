"""Every read-only dashboard route resolves and answers.

SCOPE — bucket 1 (embedder-agnostic): nothing here touches a vector space.

CLE need — the gap this closes. The dashboard had NO test of any kind, so a
route body was only ever executed by a human clicking. `/state/decisions`
shipped calling an undefined `_state_dir()` and raised NameError on every
request; the suite was green throughout, because a FastAPI route body is dead
code until something calls it.

These are deliberately shallow: status code and JSON shape, on an EMPTY state
directory. That is the point — the read paths must answer on a fresh install,
before any agent exists, and a smoke test that needs a seeded world would not
have caught the undefined name either. Depth belongs in the reads tests; this
file exists so no route body can stay unexecuted.
"""

from pathlib import Path

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

#: Read-only GET routes, with the query args they need. `/events` is excluded:
#: it is an SSE stream that does not terminate, so it needs its own test rather
#: than a request that would hang this one.
READ_ROUTES = [
    "/health",
    "/state/ps",
    "/state/candidates",
    "/state/images",
    "/state/decisions",
    "/state/topology",
    "/state/topology/versions",
]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # A fresh, empty state dir: the routes must answer before anything exists.
    monkeypatch.setenv("CLE_STATE_DIR", str(tmp_path / "cle"))
    import importlib

    from dashboard.backend import app as app_module

    importlib.reload(app_module)  # STATE_DIR is read at import time
    with fastapi_testclient.TestClient(app_module.app) as test_client:
        yield test_client


@pytest.mark.parametrize("route", READ_ROUTES)
def test_every_read_route_answers_on_an_empty_state_dir(client, route: str) -> None:
    response = client.get(route)
    assert response.status_code == 200, f"{route} -> {response.status_code}: {response.text}"
    response.json()  # raises if the body is not JSON


def test_the_route_list_covers_every_read_only_get_route() -> None:
    """The list above cannot silently fall behind the app.

    A hand-maintained route list is worthless the first time someone adds a
    route and forgets this file — so the list is checked against the app's own
    routing table rather than trusted.
    """
    import importlib

    from dashboard.backend import app as app_module

    importlib.reload(app_module)
    declared = {
        route.path
        for route in app_module.app.routes
        if "GET" in getattr(route, "methods", set())
        and route.path.startswith(("/state", "/health"))
    }
    # These two take required query args, so they cannot ride the empty-dir
    # sweep; they have their own cases below.
    parameterised = {"/state/image", "/state/topology/diff"}
    missing = declared - set(READ_ROUTES) - parameterised
    assert not missing, (
        f"read-only routes with no smoke coverage: {sorted(missing)}. "
        "Add them to READ_ROUTES — an untested route body is dead code until a "
        "human clicks it."
    )


def test_the_decisions_route_is_actually_executed(client) -> None:
    # The specific regression: this route body referenced an undefined name and
    # raised NameError on every request while the suite stayed green.
    payload = client.get("/state/decisions").json()
    assert isinstance(payload, (list, dict))


# ── the two routes that take required query args ────────────────────────────
# Written because the comment above used to CLAIM these cases existed when they
# did not — the same "naming what does not exist" pattern the repo keeps
# reproducing, this time inside a test file added to close a coverage gap.


def test_the_image_route_executes_and_reports_a_missing_hash(client) -> None:
    # A route body is dead code until something calls it (this file exists
    # because /state/decisions raised NameError on every request while the
    # suite stayed green). The assertion is that it RUNS: a 5xx here is an
    # unhandled exception, which is exactly what went unnoticed before.
    response = client.get("/state/image", params={"hash": "0" * 64})
    assert response.status_code < 500, response.text


def test_the_image_route_rejects_a_missing_query_arg(client) -> None:
    assert client.get("/state/image").status_code == 422


def test_the_topology_diff_route_executes_on_absent_versions(client) -> None:
    # Empty state dir: versions 1 and 2 do not exist. The handler catches
    # KeyError and answers 404 — a decision it makes, not a crash.
    response = client.get("/state/topology/diff", params={"a": 1, "b": 2})
    assert response.status_code < 500, response.text


def test_the_topology_diff_route_rejects_missing_query_args(client) -> None:
    assert client.get("/state/topology/diff").status_code == 422


def test_the_topology_payload_carries_the_vector_space(tmp_path) -> None:
    """The payload is a whitelist, so a new record field is absent by default.

    A topology record is required to name the vector space it was produced in
    (topology scope, invariant added with `EmbeddingConfig`), because a history
    without it is comparable to nothing. The dashboard's payload enumerates its
    fields explicitly and was written before that key existed, so it served
    `None` where the file on disk read `stub:hashed64 @ 0.6`.

    Found by comparing the live dashboard line by line against `topology.yaml`
    against a populated state, which is the only way a whitelist omission surfaces:
    nothing raises, and the field is simply absent.
    """
    import io

    from dashboard.backend import reads
    from cle.detect.clusters import HashedTokenEmbedder
    from cle.detect.embedders import embedding_config_for
    from cle.lifecycle.topology import write_topology
    from cle.oplog import OpLog
    from cle.store.backends import FileStore
    from cle.store.commits import PreEvidence

    from tests.unit.test_runtime import _build_image

    state = tmp_path / "state"
    backend = FileStore(state / "store")
    oplog = OpLog(io.StringIO())
    image = _build_image(backend, oplog)
    born_in = embedding_config_for(HashedTokenEmbedder())
    write_topology(
        backend=backend, path=state / "topology.yaml", agent="recap",
        state="trial", image_hash=image.hash,
        cause={"pre_evidence": PreEvidence(
            capture_rate=0.9, false_trigger_rate=0.02, historical_cost=4.0, window="30d",
        ).model_dump()},
        oplog=oplog, actor="human:r36", embedding=born_in,
    )

    payload = reads.topology(state)
    assert payload["embedding"] is not None, (
        "the dashboard dropped the topology's vector space; a reader cannot tell "
        "which space the states in front of them were born in"
    )
    assert payload["embedding"]["embedder_id"] == born_in.embedder_id
    assert payload["embedding"]["cluster_threshold"] == born_in.cluster_threshold


def test_every_action_routes_its_state_dir_somewhere() -> None:
    """An action that accepts `state_dir` and never reads it writes to the wrong
    place while reporting success.

    That is not hypothetical: `run_workspaces` took the parameter and dropped it,
    so `full_loop.sh` wrote its 52 oplog lines into its own default `.cle-demo`
    while the dashboard tailed `$CLE_STATE_DIR/log.jsonl`. The script exited 0.
    The board never moved. Nothing in the suite noticed, because every assertion
    about the run was true — of a directory nobody was watching.

    An unused parameter is the readable symptom, so that is what this checks.
    """
    import ast
    from pathlib import Path as _Path

    source = _Path(__file__).resolve().parents[2] / "dashboard/backend/actions.py"
    tree = ast.parse(source.read_text())

    deaf = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if "state_dir" not in {a.arg for a in node.args.args}:
            continue
        used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        if "state_dir" not in used:
            deaf.append(node.name)

    assert not deaf, (
        f"actions accept state_dir and ignore it: {deaf}. Each one acts on some "
        "other directory than the one the dashboard reads, and reports exit 0 for "
        "doing so."
    )


def test_run_test_on_the_live_state_refuses_with_an_actionable_message() -> None:
    """The Run test button on `.cle` must explain what the operator can change.

    `full_loop.sh` starts with `rm -rf` on the directory it is handed, so it
    refuses `.cle`. Left to the script, that refusal reaches the browser as
    "set CLE_DEMO_STATE to a scratch directory" after an 11 ms run — advice that
    is correct in a shell and unusable in a page, because the dashboard's state
    directory is fixed at launch by a DIFFERENT variable, `CLE_STATE_DIR`.

    What the operator saw was a button that flashed and stopped.
    """
    import asyncio
    from pathlib import Path as _Path

    from dashboard.backend import actions

    result = asyncio.run(actions.run_workspaces(_Path("/somewhere/.cle")))

    assert result["code"] == 1
    assert "CLE_STATE_DIR" in result["stderr"], (
        "the refusal must name the variable the operator can actually set"
    )
    assert result["argv"] == [], "nothing should have been spawned"


def test_run_test_on_a_scratch_state_is_not_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards the guard: a check that refused everything would pass the test
    above while breaking the button outright."""
    import asyncio
    from pathlib import Path as _Path

    from dashboard.backend import actions

    captured: dict = {}

    class _Fake:
        returncode = 0

        async def communicate(self):
            return (b"", b"")

    async def _fake_exec(*argv, **kw):
        captured["env"] = kw.get("env", {})
        return _Fake()

    # monkeypatch, not os.environ: conftest clears the ambient credentials for
    # the whole session on purpose, and a test that sets one globally hands the
    # next test an environment it did not ask for.
    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", _fake_exec)
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-not-a-real-key")
    asyncio.run(actions.run_workspaces(_Path("/somewhere/.cle-demo")))

    assert captured["env"]["CLE_DEMO_STATE"] == "/somewhere/.cle-demo", (
        "the script must be pointed at the directory the board reads"
    )


def test_the_live_stream_survives_the_state_directory_being_replaced() -> None:
    """`full_loop.sh` begins with `rm -rf`, so the log it then writes is a NEW
    file at the same path.

    The tailer used to detect only truncation, by comparing sizes. A replacement
    file that reaches the old offset before the next poll passes that check, and
    the tailer reads from a byte position belonging to a file that no longer
    exists — splicing out the middle of a line, which parses to nothing. The
    opening events of a fresh run then disappear with no error raised anywhere,
    and the board starts partway through the run it is supposed to be showing.

    Measured before the fix: of three lines written after the wipe, the first was
    lost and the other two arrived.
    """
    import asyncio
    import json
    import shutil
    import tempfile

    from dashboard.backend.oplog_sse import EventBus, tail_log_forever

    root = Path(tempfile.mkdtemp()) / "state"
    root.mkdir(parents=True)
    log = root / "log.jsonl"
    log.write_text(json.dumps({"op": "before_wipe"}) + "\n")

    async def scenario() -> list[str]:
        bus, seen = EventBus(), []
        queue = bus.subscribe()
        tailer = asyncio.create_task(tail_log_forever(log, bus))

        async def drain() -> None:
            while True:
                seen.append((await queue.get())["op"])

        drainer = asyncio.create_task(drain())
        await asyncio.sleep(0.6)
        shutil.rmtree(root)               # what full_loop.sh does first
        await asyncio.sleep(0.6)
        root.mkdir(parents=True)
        for i in range(3):
            with log.open("a") as handle:
                handle.write(json.dumps({"op": f"after_wipe_{i}"}) + "\n")
            await asyncio.sleep(0.6)
        await asyncio.sleep(0.6)
        tailer.cancel()
        drainer.cancel()
        return seen

    seen = asyncio.run(scenario())
    assert seen == ["after_wipe_0", "after_wipe_1", "after_wipe_2"], (
        f"events after the wipe: {seen}. Every line written to the replacement "
        "file must reach the stream; a missing first event is the board starting "
        "partway through a run."
    )
