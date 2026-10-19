## 5. Evidence, three stages, enforced by types

Need: cold-start (no a-priori evals), lived value, and substrate drift each
require a different standard of proof.

- **Replay → `pre_evidence`** (retrospective, zero risk): gates the build.
- **Trial → `evidence`** (lived, on natural occurrences): gates promotion.
  Mandatory field on every upward tag move.
- **Monitoring → `persistence`**: the re-validator replays the image's probe
  set when the served model changes (or on schedule when versions aren't
  exposed). Fingerprint drift → auto-demote to trial, log
  `{"op":"revalidation_failed", ...}`. Proof has an expiration date.

Three distinct Pydantic types; a function expecting `Evidence` rejects
`PreEvidence` at type level.

### 5b. A non-measurement is not a verdict

Need (added after measurement): the detector runs checks whose *soundness*
depends on the substrate. When such a check cannot run, the system must say so
rather than return a reassuring pass. Two mechanisms enforce this:

- **Three-valued stability verdict**: `stable` / `unstable` / **`unavailable`**.
  The contradiction check reports `unavailable` in any vector space its
  heuristic is not calibrated for.
- **Veto, not precondition**: an `unstable` cluster yields no candidate
  ("don't automate a self-contradicting pattern"). But `unavailable` does
  **not** block birth: the candidate is born carrying `stability="unavailable"`
  in its provenance, surfaced to the human at the override gate. Blocking on a
  check's *absence* would give it weight it never had and would stop the first
  pillar producing anything at all; a system that detects nothing is worse than
  one that proposes with a documented gap. The gap is disclosed, never silent.

Same principle as `PreEvidence != Evidence`, and as the `degenerate` resolution
diagnostic: a weak or absent measurement must never masquerade as a strong one.
