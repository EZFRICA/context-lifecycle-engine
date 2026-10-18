## The contract, six invariants

Enforced in code, pinned by property tests.

1. **Two hashes.** A candidate's `SourceSpec.hash` is never its built
   `Image.hash`. Lifecycle tags attach to image hashes only.
2. **Goodhart boundary.** A `Container` exposes no read path to its own metrics.
   Metrics are written one way to a system-owned volume.
3. **Staged builds consume nothing.** A failed resolve, replay or assemble leaves
   the store byte identical.
4. **Every operation logs one JSON line**, with a mandatory `evidence` field on
   any upward tag move. No log, no merge.
5. **Replay proves the trigger, never the answer.** Replay outputs are
   `PreEvidence` and can never flow into a promotion.
6. **Proof expires.** Images freeze a `model_fingerprint`; the re-validator
   demotes an agent when the served model drifts.

A seventh, added after measurement: **a non-measurement is never a verdict.** A
check that cannot run in the configured vector space reports `unavailable`, and
the gap is disclosed rather than passing silently.

---
