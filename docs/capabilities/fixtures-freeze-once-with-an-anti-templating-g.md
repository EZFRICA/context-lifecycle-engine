## 11. Fixtures, freeze-once, with an anti-templating guard
- **Three sources, three roles**: ground-truth (**recovery**), adversarial
  (**rejection**), holdout (**discovery**, process-independent: it imports
  nothing from `cle`). Determinism comes from the **committed `.jsonl`**, not
  from a templated generator; generators are reproducible on demand and never
  run in CI.
- **Realism guard**: asserts DATA properties grouped by the **planted intent**
  (from the sidecar), never by detected clusters: ≥8 distinct openers per
  recurring intent, no sentence >15% of messages, timing not single-valued.
- **Known debt**: the adversarial/demo source (`make_fixture.py`, the agent
  YAMLs, `full_loop.sh`, the dashboard demo) is **still templated** and excluded
  from the guard.

---
