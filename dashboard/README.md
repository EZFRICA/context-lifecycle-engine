# CLE Live Dashboard

A read-mostly window onto a running Context Lifecycle Engine, built for a
public demo: the audience watches the system detect, build, run, promote, and
re-validate agents **live**. It feeds exclusively on CLE artifacts under the
state dir (default `.cle/`), the oplog (`log.jsonl`) and whichever store the
CLI wrote (`file` or `sqlite`, selected by `$CLE_STORE`).

**Every write goes through the `cle` CLI as a subprocess**; the dashboard never
touches the store directly. Approve and Decline are the write path an audience
sees, but three maintenance actions also write, and one of them destroys: see
the API table.

## Stack
- **Backend:** FastAPI. Tails `.cle/log.jsonl` and fans it out over SSE;
  serves REST snapshots; shells out to `cle` for the single write action.
- **Frontend:** one HTML page + CSS + vanilla JS with **Alpine.js** (vendored
  locally, no CDN) and native `EventSource`. No build step, no Node.
- Zero auth, zero database, the oplog *is* the database.

## Run
```bash
uv pip install fastapi "uvicorn[standard]"        # one-time (already in the venv)
CLE_STATE_DIR=.cle-demo uv run uvicorn dashboard.backend.app:app --port 8000
# open http://localhost:8000
```

### Why `.cle-demo` and not `.cle`

Because of the **2. Run test** button, and this is a constraint on the operator
that no code enforces.

That button runs `bash examples/full_loop.sh`, and the script writes to
`${CLE_DEMO_STATE:-.cle-demo}`. It also refuses outright to run on `.cle`:

```
refusing to run on .cle - set CLE_DEMO_STATE to a scratch directory
```

That refusal is deliberate. `.cle` holds the only copy of the operator's oplog,
store and topology history, it is gitignored so git cannot restore it, and a
demo is not a reason to lose it.

The consequence is a mismatch nothing warns about. The live PULSE stream tails
`$CLE_STATE_DIR/log.jsonl`. With the dashboard on `.cle` the script writes 52 op
lines into `.cle-demo/log.jsonl` instead, exits 0, and **the board shows
nothing**: the script worked, it simply wrote somewhere the dashboard is not
watching. Silence, not an error.

So point the dashboard at the same directory the script uses. `GET /health`
reports which one it is (`state_dir`, `log_exists`) when the board looks empty
and you want to know why.
Populate some state first (`bash examples/full_loop.sh`, or `uv run python
examples/make_fixture.py` then `uv run cle build …`) so the board isn't empty.

**Launch it with the same backend the CLI wrote.** `$CLE_STORE` selects the
store for both, and the two hold different paths (`store/` vs `store.db`), so a
dashboard started on the other one reads an empty history and renders what looks
exactly like data loss.

## The four zones
- **PULSE** (top), the live oplog, one line per op, colored by op type. The
  audience literally watches the system think. `integrity_violation` renders as
  a full-width coral alert.
- **BIRTHS** (left), detected candidates as proposal cards with capture /
  false-trigger / historical-cost. **Approve** (amber, the human gate) shells
  `cle tag <agent> trial`; **Decline** shells `cle decline <agent>`. Both log
  `actor=human:dashboard`. This is the only write path.
- **LIVES** (center), images with their lifecycle state (**five** in v1:
  `archived`, `candidate`, `trial`, `ephemeral`, `pinned`; the published theory
  names more, and that divergence is recorded in `docs/BLUEPRINT.md`),
  per-container metrics side by side, and context-switch cost badges
  (`Δ blk · tok`), the founding metric of the series. A drift demotes here in
  red.
- **TOPOLOGY** (right), the learned topology as a state ladder, a two-version
  diff with per-entry evidence, and the shadow-engine strip (human tag vs the
  engine's `would:` judgment, divergences highlighted).

## Demo mode
`▶ demo` (or `POST /demo/start {pace_ms}`) walks the full loop step by step at a
readable pace, flashing the zone each step affects. It uses the **live model
path**: build and the drift revalidation call the real configured LLM
(temperature 0 for the fingerprint), so "proof expires" is a genuine substrate
change. The drift step revalidates the pinned image against a *different real
model* (`CLE_DEMO_DRIFT_MODEL`, default `gemini-3.6-flash`). Single-flight;
abortable via `POST /demo/abort`.

> The demo runs `cle clean --yes` first (wipes the state dir) and makes real
> Gemini calls: it needs credentials in `.env` and consumes quota. Run it
> deliberately, not by reflex.
>
> `cle clean` asks for confirmation when a human is at a terminal, but the
> dashboard reaches it through a subprocess with no tty, so it passes `--yes`
> and the confirmation happens in the browser instead. The state dir is
> gitignored, so nothing restores it.

## API surface
| Route | Purpose |
|---|---|
| `GET /events` | SSE; replays last 50 ops on connect, then live |
| `GET /state/ps` · `/state/candidates` · `/state/images` | snapshots |
| `GET /state/image?hash=` | one image: pre_evidence, trigger, probe count |
| `GET /state/decisions` | the op log rendered as decisions, for audit |
| `GET /state/topology?v=` · `/state/topology/versions` · `/state/topology/diff?a=&b=` | topology |
| `POST /actions/approve {agent}` · `/actions/decline {agent,reason?}` | the audience-facing write path |
| `POST /actions/init` | rebuild the demo fixture and agent |
| `POST /actions/run_workspaces` | **spends**: forces the real model (`CLE_FORCE_REAL_MODEL=1`) |
| `POST /actions/clean` | **destroys**: `cle clean --yes` on the state dir |
| `POST /demo/start {pace_ms}` · `/demo/abort` | demo runner |
| `GET /health` | liveness |

`GET /state/topology` carries an **`embedding`** field: the vector space the
history was born in (`embedder_id`, threshold, calibration). It is not optional
decoration. Centroids are only comparable inside the space that produced them,
so a reader who cannot see the space cannot interpret the states in front of
them. The payload keeps the same keys whether the store holds anything or not,
which is asserted by `tests/unit/test_dashboard_matches_disk.py`.

## Honesty & the Goodhart boundary
Replay numbers are labeled **"trigger only, not answer quality."** Demo
closures are labeled **synthetic**. The three evidence types are visually
distinct everywhere (pre_evidence blue · evidence teal · persistence
amber/coral), the type separation is a core theory claim, never blurred. And
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
