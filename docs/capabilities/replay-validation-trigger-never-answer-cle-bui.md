## 4. Replay validation, trigger, never answer (`cle/build/replay.py`)
- **`capture_rate`**: fraction of the cluster's episodes the trigger would
  intercept **against the current topology**; an incumbent owning part of the
  intent legitimately lowers it (*legacy demo*: `weekly_recap` 0.60).
- **`false_trigger_rate`**: out-of-cluster traffic the trigger would steal,
  **always** computed alongside capture. A capture rate without it is
  meaningless. (*legacy demo*: ≈0.081 recap family.)
- **`historical_cost`**: mean iterations of in-cluster episodes, abandoned
  excluded, the numeric justification of the birth.
- **Honesty**: outputs are `PreEvidence`, labelled *trigger only, not answer
  quality*; the period is carried but **not** replay-tested
  (`period_tested: false`). *Invariant 5.*
