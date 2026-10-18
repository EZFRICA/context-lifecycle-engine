## Live dashboard

```bash
uv run cle dashboard --state-dir .cle-demo --port 8000   # http://localhost:8000
```

Start on a scratch state. **"2. Run test" runs `full_loop.sh`, which deletes and
rebuilds the state directory it is given**, so it refuses `.cle` and greys the
button out. Drop `--state-dir` to watch your live state and forgo that button;
add `--store sqlite` if the CLI wrote sqlite.

One page (HTML + Alpine, no build step) served by FastAPI. Four zones: **Pulse**
(live oplog over SSE), **Births** (candidate cards with the Approve/Decline gate
and the disclosed-gap marker), **Lives**, **Topology**. Approve/Decline is the
audience-facing write path, routed through the CLI and logged as
`human:dashboard`; the operator controls (init, run test, clean, the demo) write
too, and a write sent from another site is refused. See `dashboard/README.md`.
