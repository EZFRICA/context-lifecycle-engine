## What the numbers do NOT prove

- Replay tests the **trigger only**, never answer quality; the period is
  carried but not tested.
- A fingerprint delta proves the **substrate changed**, not that the agent is
  broken.
- **Silence-demotion** is data-injected in v1, the loop is not closed.
- Demo closures are **synthetic** CLI sugar.
- `capture_rate` is relative to the **current topology**, not an absolute.
- The holdout tests' `Signal.stability` output is **not a verdict**: they call
  the ungated `detect_signal`, which never runs the contradiction check, so the
  field shows its default rather than a measured `stable`. Do not read it
  against the `unavailable` verdict documented elsewhere, they are different
  code paths, not a contradiction.
- **Detection does not recover realistic usage.** At best 2/7 planted intents
  on the GDG fixture (v1: 0/7 at *its* best across a full sweep). The clean
  three-agent result is the legacy templated source only.
- **Contradiction classification is inert in a real embedding space.** Where it
  reports `unavailable`, nothing was measured, that is not a clean bill of health.
- **The 0.775 threshold rests on ONE independent confirmation** (the holdout).
  The GDG sweep peak is *in-sample* and is not evidence.
- **The adversarial/demo source is still templated**, so every *legacy demo*
  number inherits that bias.

See `docs/METRICS.md` for per-number provenance and `docs/BLUEPRINT.md` for the
governing contract.
