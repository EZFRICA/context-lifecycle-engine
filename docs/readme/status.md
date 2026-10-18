## Status

P1 to P3 of the v1 blueprint are implemented: two-hash store, three-stage build
with replay validation, the minimal detector, the container runtime with switch
cost logging, the five-state lifecycle with a shadow engine, the topology writer,
the re-validator, a live Gemini substrate, a real embedding substrate, and the
dashboard. Known limits, stated plainly:

* Replay validates the **trigger only**, never answer quality, never the period.
* Silence-based demotion is a shadow rule whose data the runtime does not track,
  and the lifecycle engine runs in **shadow mode**: humans move tags.
* **Contradiction detection needs an operator that is not a distance** and is
  inert until it gets one; the demo fixture source is **still templated**.
* `false_trigger_rate` on the Stack Overflow corpus was 0.580 for months and is
  now 0.000: the number measured a replay that routed at 0.6 in a space
  calibrated at 0.775, not a detector that fired on everything. It still gates
  **nothing** at birth, which is the defect that remains. The facet path is a
  **pilot** integrated into nothing.

---
