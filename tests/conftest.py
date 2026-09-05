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
    any test runs, so it produces a run byte-identical to the plain one — same
    count, same duration — and reports success for a measurement that never
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
