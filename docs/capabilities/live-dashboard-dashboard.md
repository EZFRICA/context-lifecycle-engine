## 8. Live dashboard (`dashboard/`)
FastAPI + SSE + a single Alpine page (no build step). Four zones, **Pulse**
(live oplog), **Births** (proposal cards with the human Approve/Decline gate),
**Lives** (5-state images, per-container metrics, switch-cost badges, drift
card), **Topology** (state ladder, shadow strip, version diff). Read-mostly:
the audience's writes are Approve/Decline, the operator controls (init, run
test, clean, the demo) write too, every write goes through the CLI and is
logged as `human:dashboard`, and a write sent from another site is refused
before any route runs. Metrics shown are the human's window, never fed back to
an agent.
- **Disclosed-gap marker on Births cards**: when a candidate's contradiction
  check could not run in its vector space, the card shows a dashed *"⚠
  contradiction check did not run"* marker, deliberately **not** styled as an
  evidence badge (it is an absence, not a measurement). Derived at read time
  from `image.trigger.embedder_id` via the classifier's own predicate, no new
  write path, so card and signal gate cannot disagree.
