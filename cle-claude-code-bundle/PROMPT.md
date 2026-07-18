# Kickoff — paste into Claude Code (plan mode)

Read CLAUDE.md, docs/BLUEPRINT.md, and both skills before proposing anything.

Mission: implement CLE v1, phase P1 — two-hash store, three-stage build with
replay validation, minimal detector. Python 3.12, Pydantic v2, pytest +
hypothesis, typer, storage behind a Protocol with InMemoryStore as default.

Sequence I want:
1. Propose the P1 plan: module by module, the order you'll build them, and
   which property tests you'll write FIRST (TDD on invariants is mandatory —
   the six tests in cle-core-contracts come before the code they guard).
   Wait for my approval.
2. Scaffold: pyproject, repo layout from BLUEPRINT §2, empty modules with
   docstrings stating each module's contract, CI-ready pytest config.
3. Build in this order: store → build (resolve, replay, assemble) → detect.
   One commit per feature, each with its log line and tests.
4. Exit demo for P1: `cle build examples/weekly_recap_agent.yaml
   --replay-window 30d` against a synthetic prompt-history fixture, printing
   capture_rate, false_trigger_rate, historical_cost, and the two hashes
   (source ≠ image).

Constraints that override any instinct you have:
- The governance rule: no component justified only by "Docker has it".
- Replay proves the trigger, never answer quality — language included.
- Container never reads its own metrics.
- A feature without its JSON log line doesn't merge.
- When the blueprint is ambiguous, ask; when it's silent, propose in ≤5 lines
  and wait.

Use the cle-reviewer subagent after each feature, before committing.
Settle BLUEPRINT §9 open decision 1 (episode silence threshold) in your P1
plan proposal — argue your choice in ≤5 lines.
