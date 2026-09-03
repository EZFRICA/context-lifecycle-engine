---
name: cle-dashboard
description: Data contracts, API surface, and page composition for the CLE live dashboard. Use when designing or implementing the FastAPI backend, the SSE stream, or any Alpine.js component that renders oplog events, images, containers, or topology.
---

# CLE Dashboard Contract

## Source of truth
Everything renders from two read-only sources:
- `.cle/log.jsonl` — the oplog. One JSON object per line:
  `{"op", "ts", "actor", "image", "from", "to",
    "evidence"|"pre_evidence"|"persistence", "latency_ms", ...}`.
  Ops emitted in v1: build, run, switch, tag, revalidate,
  closure_distribution, cluster_stability, revalidation_failed,
  topology_write, integrity_violation, detector_observing,
  candidate_declined, and engine shadow lines
  (`actor: "engine:shadow"`, field `would`).
- FileStore under `.cle/` — images (probe_set, pre_evidence, trigger),
  tag refs (`agents/<name>/<state>`, `agents/<name>/v<semver>`),
  topology versions (`topology/v<n>`, parent-chained).
The dashboard must tolerate unknown ops (render raw in PULSE) — the CLE
will grow; the dashboard must not crash on new event types.

## Backend surface
- `GET /events` — SSE. Tails log.jsonl from offset; replays last N on
  connect (N=50) so the UI is never empty. Event name = op.
- `GET /state/ps` — running containers with metrics (shell `cle ps --json`
  if available, else parse run/switch ops from the log).
- `GET /state/candidates` — images in candidate state + their PreEvidence.
- `GET /state/images` — all images with current lifecycle tag and version.
- `GET /state/topology?v=` — one topology version, parsed. The payload MUST
  carry `embedding` (the vector space the history was born in). It is built as
  an explicit whitelist, which is how the field went missing until R36: the
  reader could not tell which space the states in front of them came from.
- `GET /state/topology/diff?a=&b=` — the delta with per-entry evidence.
- `POST /actions/approve {agent}` → runs `cle tag <agent> trial`,
  env actor=human:dashboard. `POST /actions/decline {agent}` → runs
  `cle decline <agent>` (the command exists; it logs `candidate_declined`
  and moves no tag). NO other POST route may exist — the single-write-path
  rule is what keeps the dashboard read-mostly.

## Rendering rules (contract, not style)
- Evidence types are visually distinct EVERYWHERE: pre_evidence (blue),
  evidence (teal), persistence (amber/red on failure). Never render one
  styled as another — the type separation is a core theory claim.
- Switch events always show diff_blocks + diff_tokens as badges. A switch
  without visible cost defeats the point of the metric.
- Shadow strip: pair each human tag op with the nearest engine:shadow
  `would` on the same image; agreement renders muted, divergence highlighted
  with both verdicts side by side.
- Every replay-derived number carries the inline caption
  "trigger only — not answer quality". Every demo-mode closure carries
  "synthetic". Copy comes from docs/METRICS.md wording.
- FIVE lifecycle states exist in the code (archived, candidate, trial,
  ephemeral, pinned) and each has a fixed color (visual-identity skill).
  The published part-7 machine names more (`pattern`, `deprecated`); the UI
  must NOT invent chips for states the store cannot hold.
- integrity_violation renders as a full-width alert in PULSE. It is the
  security story; it must never be visually minor.
- **Disclosed gap on Births cards.** When a candidate's contradiction check
  could not run in its vector space (`image.stability_checked === false`,
  derived server-side from `trigger.embedder_id`), the card shows a marker
  saying so. It is styled as an ABSENCE — dashed, amber, never an evidence
  badge — because it is a missing measurement, not a measured value. A human
  must not approve believing the cluster was checked and found clean.

## Demo mode
Backend endpoint `POST /demo/start {pace_ms}` executes full_loop.sh steps
via subprocess, emitting a `demo_step` SSE event (step number + title)
before each. Frontend: step title banner + flash on the affected zone.
Abortable. Never run two demos concurrently (lock file).
