"""FastAPI app - SSE + snapshot REST + the write routes + demo runner.

Writes are Approve/Decline (the audience's) and the operator controls (init,
run test, clean, the demo), each through the CLI; a write sent from another
site is refused before any route runs (`refuse_cross_origin_writes`).

Run:  cle dashboard --state-dir .cle-demo --port 8000

That subcommand exports CLE_STATE_DIR and calls uvicorn on this module, so
running uvicorn directly works too - but then the state directory comes from
the ambient CLE_STATE_DIR (default `.cle/`) rather than from a flag, which is
the reading everything else in the docs assumes. Serves the Alpine frontend
at /.

Use a scratch directory, not `.cle`, if you intend to press "2. Run test":
that button deletes and rebuilds the state it runs on, and refuses `.cle`.
"""

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cle.lifecycle.reasons import HumanDeclineReason
from cle.logs import configure_logging

from . import reads
from .demo import DemoRunner, ScriptRunner
from .oplog_sse import EventBus, event_stream, tail_log_forever

STATE_DIR = Path(os.getenv("CLE_STATE_DIR", ".cle")).resolve()
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
LOG_PATH = STATE_DIR / "log.jsonl"

bus = EventBus()
demo_runner = DemoRunner(bus, STATE_DIR)
script_runner = ScriptRunner(bus, STATE_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    # The dashboard is an application: it configures logging, importing a cle
    # module does not (cle/logs.py). In the lifespan rather than at import, so
    # uvicorn's own configuration is already in place and ours is added to it.
    configure_logging()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tailer = asyncio.create_task(tail_log_forever(LOG_PATH, bus))
    try:
        yield
    finally:
        tailer.cancel()


app = FastAPI(title="CLE Live Dashboard", lifespan=lifespan)

#: Methods that change nothing. Every other request is a write.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: An object address, as the CLI spells it (`cle/cli/main.py`) and as the store
#: now enforces it (`assert_object_address`).
_HASH = re.compile(r"^[0-9a-f]{64}$")


@app.middleware("http")
async def refuse_cross_origin_writes(request: Request, call_next):
    """A write must come from this page, never from another site.

    The dashboard serves its own frontend, so it needs no CORS at all; it used
    to allow every origin, and the POST routes include `clean`, which deletes
    the state. Removing CORS is not enough on its own: a POST with no body is a
    "simple" request, which a browser sends cross-origin without asking. A
    browser always names the page's origin on such a request, so a write whose
    `Origin` is not this server is refused before any route runs. A client that
    sends no `Origin` (curl, the tests) is not a page in someone's browser, and
    is let through.
    """
    origin = request.headers.get("origin")
    if request.method not in _SAFE_METHODS and origin is not None:
        if urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse(status_code=403, content={"detail": "cross-origin write refused"})
    return await call_next(request)


# --- live stream ------------------------------------------------------------


@app.get("/events")
async def events() -> StreamingResponse:
    return StreamingResponse(
        event_stream(LOG_PATH, bus),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- snapshots (read-only) --------------------------------------------------


@app.get("/state/ps")
def state_ps():
    return reads.ps(STATE_DIR)


@app.get("/state/candidates")
def state_candidates():
    return reads.candidates(STATE_DIR)


@app.get("/state/images")
def state_images():
    return reads.images(STATE_DIR)


@app.get("/state/image")
def state_image(hash: str):
    # Refused at the route as well as in the store. The store's guard is the one
    # that matters (`assert_object_address`); this one keeps a malformed address
    # from reaching an exception handler that turns it into prose, and answers
    # 400 rather than a 200 carrying an `error` field, which is what a bad
    # request is.
    if not _HASH.match(hash):
        raise HTTPException(status_code=400, detail="hash must be 64 hex characters")
    return reads.image_detail(STATE_DIR, hash)


@app.get("/state/decisions")
def state_decisions():
    """Read-only second view over the same log - no new write path."""
    return reads.decisions(STATE_DIR)


@app.get("/state/topology")
def state_topology(v: int | None = None):
    return reads.topology(STATE_DIR, v)


@app.get("/state/topology/versions")
def state_topology_versions():
    return reads.topology_versions(STATE_DIR)


@app.get("/state/topology/diff")
def state_topology_diff(a: int, b: int):
    try:
        return reads.topology_diff(STATE_DIR, a, b)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error))


# --- writes: the audience's path, then the operator controls ----------------


class AgentBody(BaseModel):
    agent: str


class DeclineBody(BaseModel):
    agent: str
    # Closed vocabulary, not prose. The CLI would refuse free text anyway
    # (UnknownReasonError), but refusing it at the HTTP edge means the boundary
    # is a type on every surface rather than a check on one of them.
    reason: HumanDeclineReason | None = None


@app.post("/actions/approve")
async def actions_approve(body: AgentBody):
    from .actions import approve

    return await approve(body.agent, STATE_DIR)


@app.post("/actions/decline")
async def actions_decline(body: DeclineBody):
    from .actions import decline

    return await decline(body.agent, body.reason, STATE_DIR)


@app.post("/actions/init")
async def actions_init():
    from .actions import init_system

    return await init_system(STATE_DIR)


@app.post("/actions/run_workspaces")
async def actions_run_workspaces():
    """Start `full_loop.sh` in the background and return at once.

    This used to await the subprocess, so the request held open for the whole
    run - 26 s on stub models, 131 s measured on real ones - with every control
    on the page disabled and nothing printed until the end. Progress now arrives
    as `demo_step` events on the same SSE stream the rest of the board reads, and
    the button is released by the terminal event rather than by the response.
    """
    from .actions import demo_run_env

    prepared = demo_run_env(STATE_DIR)
    if "env" not in prepared:
        return prepared  # refusal, unchanged in shape and content
    if not script_runner.start(prepared["env"]):
        raise HTTPException(status_code=409, detail="a run is already in progress")
    return {"status": "started", "state_dir": str(STATE_DIR)}


@app.post("/actions/abort_run")
def actions_abort_run():
    """Stop a run in progress. Idempotent: aborting nothing is not an error."""
    script_runner.abort()
    return {"status": "aborting"}


@app.post("/actions/clean")
async def actions_clean():
    from .actions import clean_system

    return await clean_system(STATE_DIR)


# --- demo -------------------------------------------------------------------


class DemoBody(BaseModel):
    pace_ms: int = 3000


@app.post("/demo/start")
def demo_start(body: DemoBody):
    started = demo_runner.start(body.pace_ms)
    if not started:
        raise HTTPException(status_code=409, detail="a demo is already running")
    return {"status": "started", "pace_ms": body.pace_ms}


@app.post("/demo/abort")
def demo_abort():
    demo_runner.abort()
    return {"status": "aborting"}


@app.get("/health")
def health():
    # `demo_blocked` comes from the same predicate the action itself uses, so the
    # page can never offer a button the backend would refuse.
    from .actions import demo_run_refusal

    blocked = demo_run_refusal(STATE_DIR)
    return {
        "ok": True,
        "state_dir": str(STATE_DIR),
        "log_exists": LOG_PATH.exists(),
        "demo_runnable": blocked is None,
        "demo_blocked": blocked,
        "run_in_progress": script_runner.running,
    }


class _RevalidatingStaticFiles(StaticFiles):
    """StaticFiles that asks the browser to revalidate instead of guessing.

    `StaticFiles` sends `etag` and `last-modified` but no `Cache-Control`, so a
    browser falls back to HEURISTIC freshness: it may reuse a cached copy for a
    while without asking. The asset URLs carry no version, so there is nothing to
    invalidate them either.

    The visible consequence, and the reason this exists: a stylesheet fix shipped,
    the server served it, and an operator with the page already open kept seeing
    the old rendering - a button that read as disabled. Nothing was wrong on
    either side; the fix simply never crossed.

    `no-cache` does not mean "do not cache". It means "revalidate before use", so
    the etag still turns almost every load into a 304. That is the right trade
    for a dashboard whose frontend is edited while it runs.
    """

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Static frontend LAST so explicit API routes above take precedence.
if FRONTEND_DIR.exists():
    app.mount(
        "/", _RevalidatingStaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend"
    )
