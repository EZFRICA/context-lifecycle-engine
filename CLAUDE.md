# CLE — Context Lifecycle Engine (v1)

Reference implementation of the theory published in the Agent OS series
(parts 7–8). Theory docs: `docs/BLUEPRINT.md` is the contract; when code and
blueprint disagree, stop and ask, don't improvise.

## What this system is

A system with two cardinal pillars, both present from v1:
1. **Detection** — the system detects candidate agents from user usage
   (intent clustering + recurrence counting).
2. **Lifecycle** — candidates are built, replay-validated, trialed, promoted,
   demoted, archived, resurrected. Evidence-driven, never prediction-driven.

The CLE is the system. Docker is one of the vocabularies it borrows
(build/image/container/volumes/topology), Git another (Merkle store), the APU
series a third (the block auto-detection mechanism, promoted from memory blocks
to whole agents). We borrow notions that serve the system and leave the rest.

## Governance rule (applies to every design decision)

Every component must cite the CLE need that justifies it. A component justified
only by "Docker has it" is rejected. This applies to you: never add a feature,
field, or abstraction because the analogy suggests it.

## Non-negotiable invariants (enforced in code, tested by property)

1. **Two hashes.** `SourceSpec.hash != Image.hash`, always. Lifecycle tags
   attach to Image hashes only; tagging a source hash raises `TagTargetError`.
2. **Goodhart boundary.** `Container` exposes NO read path to its own metrics.
   No method, no property, no injected context. Metrics live in a system
   volume owned by the runtime.
3. **Staged builds consume nothing.** A failed resolution/validation/replay
   burns zero trial occurrences and writes nothing except the build log.
4. **Every lifecycle op logs one JSON line** with a mandatory `evidence` field
   on upward transitions. Format in the core-contracts skill. No log, no merge.
5. **Replay validates the trigger, never the answer quality.** Replay outputs
   are labeled `pre_evidence`, distinct from trial `evidence`. Conflating the
   two in code or logs is a review-blocking error.
6. **Proof expires.** Images record `model_fingerprint` at build; the
   re-validator can demote on fingerprint drift. Promotion is never final.

## Stack

Python 3.12, Pydantic v2 (frozen models for immutables), pytest + hypothesis
for property tests, typer for the CLI, asyncio for background work.
Storage behind a Protocol: `InMemoryStore` (tests, default) and `WeaviateStore`
(client v4). No test may require Weaviate.

## Workflow

- Plan before code on any task touching `store/`, `build/`, or `lifecycle/`.
  Present the plan, wait for approval.
- TDD for invariants: write the property test that enforces the invariant
  first, then the code.
- Small commits, Conventional Commits. One feature + its log line + its tests
  per commit.
- Descriptive variable names, inline reasoning comments (the maintainer reads
  code as prose).
- When a blueprint decision is ambiguous, ask; when it's absent, propose in
  ≤5 lines and wait.

## Phases (v1 = P1 → P3, vertical slices of both pillars)

- **P1** — two-hash store · three-stage build **including replay validation** ·
  minimal detector (embedding clusters + recurrence counts). Exit: `cle build
  --replay-window 30d` on a detected candidate prints capture rate, false
  triggers, historical cost.
- **P2** — runtime: containers, mounts (ro/rw scopes, MCP handles), metrics
  volume behind the Goodhart boundary. Exit: one image, two workspaces,
  `cle ps` shows divergent per-container metrics.
- **P3** — lifecycle tags + engine (shadow mode: humans move tags, engine logs
  what it would do) · `topology.yaml` writer (every change is a commit with
  evidence) · re-validator (probe replay on model change → auto-demote to
  trial). Exit: `cle diff` between two topology versions.

## Measurements are a deliverable

Per build: duration + failure-stage distribution. Per container:
solicitations, iterations, closure tags. Per lifecycle op: evidence payload.
Per topology version: diff size. Shadow-mode divergence (human vs engine tag
decisions). These logs are the raw material of article 9 — a feature without
its log line doesn't merge.
