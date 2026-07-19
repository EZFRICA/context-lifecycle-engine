# CLE Live Dashboard

A read-mostly window onto a running Context Lifecycle Engine, built for a
public demo: the audience watches the system detect, build, run, promote, and
re-validate agents **live**. It feeds exclusively on CLE artifacts under the
state dir (default `.cle/`) — the oplog (`log.jsonl`) and the FileStore — and
has exactly **one write path** (Approve / Decline), routed through the `cle`
CLI so the store is never touched directly.

## Stack
- **Backend:** FastAPI. Tails `.cle/log.jsonl` and fans it out over SSE;
  serves REST snapshots; shells out to `cle` for the single write action.
- **Frontend:** one HTML page + CSS + vanilla JS with **Alpine.js** (vendored
  locally, no CDN) and native `EventSource`. No build step, no Node.
- Zero auth, zero database — the oplog *is* the database.

## Run
```bash
uv pip install fastapi "uvicorn[standard]"        # one-time (already in the venv)
CLE_STATE_DIR=.cle uv run uvicorn dashboard.backend.app:app --port 8000
# open http://localhost:8000
```
Populate some state first (`bash examples/full_loop.sh`, or `uv run python
examples/make_fixture.py` then `uv run cle build …`) so the board isn't empty.

## The four zones
- **PULSE** (top) — the live oplog, one line per op, colored by op type. The
  audience literally watches the system think. `integrity_violation` renders as
  a full-width coral alert.
- **BIRTHS** (left) — detected candidates as proposal cards with capture /
  false-trigger / historical-cost. **Approve** (amber — the human gate) shells
  `cle tag <agent> trial`; **Decline** shells `cle decline <agent>`. Both log
  `actor=human:dashboard`. This is the only write path.
- **LIVES** (center) — images with their lifecycle state (seven states),
  per-container metrics side by side, and context-switch cost badges
  (`Δ blk · tok`) — the founding metric of the series. A drift demotes here in
  red.
- **TOPOLOGY** (right) — the learned topology as a state ladder, a two-version
  diff with per-entry evidence, and the shadow-engine strip (human tag vs the
  engine's `would:` judgment, divergences highlighted).

## Demo mode
`▶ demo` (or `POST /demo/start {pace_ms}`) walks the full loop step by step at a
readable pace, flashing the zone each step affects. It uses the **live model
path**: build and the drift revalidation call the real configured LLM
(temperature 0 for the fingerprint), so "proof expires" is a genuine substrate
change. The drift step revalidates the pinned image against a *different real
model* (`CLE_DEMO_DRIFT_MODEL`, default `gemini-1.5-flash`). Single-flight;
abortable via `POST /demo/abort`.

> The demo runs `cle clean` first (wipes `.cle/`) and makes real Gemini calls —
> needs a valid `GEMINI_API_KEY` in `.env` and consumes quota. Run it
> deliberately, not by reflex.

## API surface
| Route | Purpose |
|---|---|
| `GET /events` | SSE; replays last 50 ops on connect, then live |
| `GET /state/ps` · `/state/candidates` · `/state/images` | snapshots |
| `GET /state/topology?v=` · `/state/topology/versions` · `/state/topology/diff?a=&b=` | topology |
| `POST /actions/approve {agent}` · `/actions/decline {agent,reason?}` | the one write path |
| `POST /demo/start {pace_ms}` · `/demo/abort` | demo runner |

## Honesty & the Goodhart boundary
Replay numbers are labeled **"trigger only — not answer quality."** Demo
closures are labeled **synthetic**. The three evidence types are visually
distinct everywhere (pre_evidence blue · evidence teal · persistence
amber/coral) — the type separation is a core theory claim, never blurred. And
the metrics shown here are the **human's** window: the dashboard reads them, but
nothing here is ever fed back to an agent. Reads import CLE's own read helpers;
only Approve/Decline (and the demo) write, always through the CLI, always
logged.

## Layout
```
dashboard/
  backend/   app.py · oplog_sse.py · reads.py · actions.py · demo.py
  frontend/  index.html · styles.css · app.js · vendor/alpine.min.js
```
