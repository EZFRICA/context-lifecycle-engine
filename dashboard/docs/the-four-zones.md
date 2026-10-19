## The four zones
- **PULSE** (top), the live oplog, one line per op, colored by op type. The
  audience literally watches the system think. `integrity_violation` renders as
  a full-width coral alert.
- **BIRTHS** (left), detected candidates as proposal cards with capture /
  false-trigger / historical-cost. **Approve** (amber, the human gate) shells
  `cle tag <agent> trial`; **Decline** shells `cle decline <agent>`. Both log
  `actor=human:dashboard`. This is the audience-facing write path; the operator
  controls listed under the API surface write as well.
- **LIVES** (center), images with their lifecycle state (**five** in v1:
  `archived`, `candidate`, `trial`, `ephemeral`, `pinned`; the published theory
  names more, and that divergence is recorded in `docs/BLUEPRINT.md`),
  per-container metrics side by side, and context-switch cost badges
  (`Δ blk · tok`), the founding metric of the series. A drift demotes here in
  red.
- **TOPOLOGY** (right), the learned topology as a state ladder, a two-version
  diff with per-entry evidence, and the shadow-engine strip (human tag vs the
  engine's `would:` judgment, divergences highlighted).
