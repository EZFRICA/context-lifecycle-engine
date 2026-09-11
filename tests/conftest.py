"""Suite-wide isolation from the operator's shell.

The suite claims to be offline and deterministic. It was neither, in one
specific way: three environment variables select the store backend, the vector
space, and the vector cache path, and every one of them is read at call time by
production code the tests exercise.

A test that constructs `FileStore(...)` explicitly and then calls
`reads.topology(state)` gets whatever backend `$CLE_STORE` names, because that
is how `open_store` resolves. With `CLE_STORE=sqlite` exported, six dashboard
tests read an empty SqliteStore over a FileStore directory and fail. The suite
was green on one developer's shell and red on another's, for a reason no test
named.

`examples/full_loop.sh CLE_STORE=sqlite ...` is the case that surfaced it: the
script exports the variable for its own subprocess calls and then runs the bare
suite in that same shell.

So the environment is cleared once, for the whole session. A test that wants a
non-default backend or embedder sets it itself, explicitly, with monkeypatch,
which is also the only way a reader can tell that it did.
"""

import os

import pytest

#: Read by production code at call time, so ambient values leak into assertions.
#: `CLE_ACTOR` is included because it lands in oplog lines that tests compare.
AMBIENT = ("CLE_STORE", "CLE_EMBEDDER", "CLE_VECTOR_CACHE", "CLE_STATE_DIR",
           "CLE_ACTOR", "CLE_FORCE_REAL_MODEL")


@pytest.fixture(autouse=True, scope="session")
def _neutral_environment():
    """Clear the selection variables, and stop `.env` from putting them back.

    Clearing alone is not enough, and the way it fails is instructive.
    `cle/llm_provider.py` calls `load_dotenv()` at MODULE scope, so the first
    test that imports it (directly, or through `cle.cli.main` reaching the
    fingerprinter) re-reads `.env` and repopulates whatever it holds. On a
    machine whose `.env` carries `CLE_FORCE_REAL_MODEL`, the fingerprinter then
    raises on a failed probe instead of falling back to its offline hash, and
    WHICH tests notice depends on collection order. The suite goes
    intermittently red with failures that look unrelated to the cause.

    So `load_dotenv` is neutralised for the session. That is not a workaround
    around the isolation, it IS the isolation: a suite that claims to be offline
    by construction must not read the operator's credentials file at all, and
    the tests that need a variable set it themselves with monkeypatch.

    CONSEQUENCE, and it surprises people: **the suite cannot be aimed at a live
    substrate from outside.** `CLE_EMBEDDER=real pytest` is popped here before
    any test runs, so it produces a run byte-identical to the plain one - same
    count, same duration - and reports success for a measurement that never
    happened. There is no flag that makes the suite live, by design.

    Live coverage comes from the CLI and script paths, which DO read these
    variables: `cle build --embedder real`, `examples/full_loop.sh` with real
    model ids, `cle revalidate --model-id current`. Those are the surfaces to
    point at a served model; this one is frozen on purpose.
    """
    import dotenv

    saved = {name: os.environ.pop(name, None) for name in AMBIENT}
    real_load = dotenv.load_dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False
    try:
        yield
    finally:
        dotenv.load_dotenv = real_load
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value


# ── the bucket probe (tools/buckets.py) ─────────────────────────────────────
# Records which embedder each test invokes: in its body, in any fixture it
# depends on, or when its module is imported. Off unless `CLE_BUCKET_REPORT`
# names a file, so an ordinary run is untouched. The context is a stack because
# a fixture is set up INSIDE the protocol of the first test that requests it.
#
# A REGISTERED PLUGIN, not conftest-level hooks. A conftest's hooks are scoped to
# its directory, and pytest calls `pytest_fixture_setup` for a session-scoped
# fixture on the Session node, at the repository root, where this file's hooks
# are not visible. Written as bare hooks, the probe never saw the session
# fixture `gdg` being set up: its embeddings landed on whichever test happened
# to request it first, and every later user of it measured as embedding nothing.

_BUCKET_REPORT = os.environ.get("CLE_BUCKET_REPORT")


class _BucketProbe:
    def __init__(self, report: str) -> None:
        self.report = report
        self.context: list[tuple] = []
        self.calls: dict[tuple, set[str]] = {}

    def record(self, embedder_id: str) -> None:
        key = self.context[-1] if self.context else ("session",)
        self.calls.setdefault(key, set()).add(embedder_id)

    def _within(self, key: tuple):
        self.context.append(key)
        try:
            yield
        finally:
            self.context.pop()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_make_collect_report(self, collector):
        if isinstance(collector, pytest.Module):
            yield from self._within(("module", str(collector.path)))
        else:
            yield

    @pytest.hookimpl(hookwrapper=True)
    def pytest_fixture_setup(self, fixturedef, request):
        yield from self._within(("fixture", fixturedef.baseid, fixturedef.argname))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        yield from self._within(("test", item.nodeid))

    def pytest_sessionfinish(self, session, exitstatus):
        import json
        from pathlib import Path

        records = {}
        for item in session.items:
            keys = [("test", item.nodeid), ("module", str(item.path))]
            info = getattr(item, "_fixtureinfo", None)
            for defs in (info.name2fixturedefs.values() if info else ()):
                keys.extend(("fixture", d.baseid, d.argname) for d in defs)
            used = set().union(*(self.calls.get(k, set()) for k in keys))
            records[item.nodeid] = {"embedders": sorted(used),
                                    "stub_only": item.get_closest_marker("stub_only") is not None}
        Path(self.report).write_text(json.dumps(records))


def pytest_configure(config):
    if not _BUCKET_REPORT:
        return
    from cle.detect import clusters, embedders

    probe = _BucketProbe(_BUCKET_REPORT)
    for cls in (clusters.HashedTokenEmbedder, embedders.CachedEmbedder, embedders.RealEmbedder):
        original = cls.embed

        def probed(self, text, _original=original):
            probe.record(getattr(self, "embedder_id", type(self).__name__))
            return _original(self, text)

        cls.embed = probed
    config.pluginmanager.register(probe, "cle-bucket-probe")
