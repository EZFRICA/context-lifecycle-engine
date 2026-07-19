"""FastAPI app — SSE + snapshot REST + the one write path + demo runner.

Run:  uvicorn dashboard.backend.app:app --port 8000
State dir via CLE_STATE_DIR (default .cle/). Serves the Alpine frontend at /.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import reads
from .demo import DemoRunner
from .oplog_sse import EventBus, event_stream, tail_log_forever

STATE_DIR = Path(os.getenv("CLE_STATE_DIR", ".cle")).resolve()
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
LOG_PATH = STATE_DIR / "log.jsonl"

bus = EventBus()
demo_runner = DemoRunner(bus, STATE_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tailer = asyncio.create_task(tail_log_forever(LOG_PATH, bus))
    try:
        yield
    finally:
        tailer.cancel()


app = FastAPI(title="CLE Live Dashboard", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


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
    return reads.image_detail(STATE_DIR, hash)


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


# --- the ONE write path -----------------------------------------------------


class AgentBody(BaseModel):
    agent: str


class DeclineBody(BaseModel):
    agent: str
    reason: str | None = None


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
    from .actions import run_workspaces

    return await run_workspaces(STATE_DIR)


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
    return {"ok": True, "state_dir": str(STATE_DIR), "log_exists": LOG_PATH.exists()}


# Static frontend LAST so explicit API routes above take precedence.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
