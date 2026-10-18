## 6. Lifecycle, the second pillar (`cle/lifecycle`)
- **Five-state ladder**: `archived(0) → candidate(1) → trial(2) →
  ephemeral(3) → pinned(4)`. Transitions are not an enumerated set: `move_tag`
  accepts any pair inside `STATE_RANK`, gated by rank + proof, a move into
  `ephemeral`/`pinned` demands lived `Evidence`, any other upward move demands
  `pre_evidence`, and every downward move demands a logged reason. Resurrection
  (`archived → trial`) works because `archived` ranks 0. Immutable
  `v<semver>` refs are a separate write-once namespace, not a state.
- **KNOWN DIVERGENCE from the published theory**: part 7 defines **seven**
  states; the code implements **five**. `pattern` and `deprecated` have **zero
  code representation**: no `STATE_RANK` entry, no literal anywhere in `cle/`,
  no tag ref, and no dashboard chip. (`deprecated` still has an orphan CSS rule
  in the dashboard stylesheet, dead style, never applied.) The engine's shadow
  verdicts are `hold`, `trial`, `ephemeral`, `pinned`, `archived`,
  `demote_silence`: again no `pattern`, no `deprecated`. This is a v1 gap
  recorded as such, not a renaming of the theory.
- **Three standards of proof, type-separated**: `PreEvidence` (replay),
  `Evidence` (trial, lived), `Persistence` (drift). The promotion API rejects
  the other two at type level.
- **Shadow engine**: runs the part-7 thresholds and logs `actor:engine:shadow`
  with `would:`; it never writes a ref. The human/engine divergence log is the
  calibration set for going live.
- **Silence-demotion**: a shadow rule, **data-injected** in v1; the runtime
  does not yet track last-solicitation. The loop is not closed.
- **Topology writer**: the sole author of `topology.yaml`; every change is a
  store commit under `topology/v<n>` carrying its cause.
- **Re-validation & proof expiry**: replays the frozen probe set against the
  served model; drift → `revalidation_failed` + auto-demote. **Deliberate
  conservatism**: a *better* model demotes too, because the fingerprint is a
  change detector, not a quality detector.
- **Drift-born succession**: a v2 rebuilt on the drifted substrate is a
  distinct image with a distinct fingerprint, causally born from the drift.
