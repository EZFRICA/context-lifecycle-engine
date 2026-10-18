## A non-measurement is never a verdict
When a check's soundness depends on the substrate, it must say so rather than
return a reassuring pass:
- the stability verdict is THREE-valued: `stable` / `unstable` / `unavailable`;
- `unstable` VETOES a birth; `unavailable` does NOT - the candidate is born
  carrying `stability="unavailable"` in its provenance, disclosed to the human
  at the override gate. Blocking on a check's *absence* would give it weight it
  never had and would stop the first pillar producing anything at all.
Same principle as `PreEvidence != Evidence` and the `degenerate` resolution
diagnostic. Never record `stability="stable"` when the check did not run.
