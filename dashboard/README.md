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


- [Stack](docs/stack.md) - serves REST snapshots; shells out to `cle` for the single write action.
- [Run](docs/run.md) - uv pip install fastapi "uvicorn[standard]"        # one-time (already in the venv)
- [The four zones](docs/the-four-zones.md) - audience literally watches the system think. `integrity_violation` renders as
- [Demo mode](docs/demo-mode.md) - `▶ demo` (or `POST /demo/start {pace_ms}`) walks the full loop step by step at a
- [API surface](docs/api-surface.md) - Every route that is not a GET is a write, and a write whose `Origin` header is
- [Honesty & the Goodhart boundary](docs/honesty-the-goodhart-boundary.md) - Replay numbers are labeled **"trigger only, not answer quality."** Demo
- [Layout](docs/layout.md) - dashboard/
