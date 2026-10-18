## Era A, the legacy templated demo (`examples/full_loop.sh`)

Produced by `make_fixture.py`, which has **not** been de-templated. These
numbers describe *mechanics* and are reproducible offline (`CLE_MODEL_A/B=stub-*`).

### Build

| Metric | Value | Source & scope |
|---|---|---|
| `capture_rate` | `weekly_recap` **0.60**, others 1.00 | `cle/build/replay.py`. 0.60 because the hand-authored `status_report` incumbent already owns 2 of its 5 reworded episodes, capture is measured **against the current topology**, not in a vacuum. |
| `false_trigger_rate` | **≈ 0.081** (recap family), 0.0 others | Out-of-cluster episodes the trigger would steal. The adversarial window plants one firing "bridge" + 4 near-miss traps that are correctly rejected (0.091 with the bridge alone → 0.081 once the traps enlarge the denominator). |
| `historical_cost` | recap 3.4, standup 2.7, incident 7.0 it/ep | Mean iterations of in-cluster episodes, **abandoned excluded** (anti-Goodhart: an agent that induces abandonment must not profit from fewer counted iterations). |
| `closure_distribution` | per-agent success/reformulated/abandoned | One op line per successful replay. |

*Pinned by* `test_replay.py` (both rates always computed, determinism,
competition lowers capture), `test_adversarial_fixture.py` (non-zero false
trigger). **Era-A caveat**: the bridge fires because it *shares tokens*, not
because it is semantically close.

### Runtime

- **Switch cost** `diff_blocks` **4** / `diff_tokens` **127**: symmetric
  difference of resolved block hashes on a real `weekly_recap → incident_triage`
  swap (disjoint component sets). *`test_runtime.py::test_ensure_run_and_switch_with_costs`.*
- **Per-container metrics**: one image, two workspaces, genuinely divergent
  counts; written one-way through `MetricsVolume.record()`. The container has
  **no read path** to them. *`test_goodhart_boundary.py` (5 reflection tests).*

### Lifecycle

- **Shadow divergence**: human promotes `standup_digest` to `ephemeral` on
  `cost_ratio 0.95`; the engine logs `would: hold` (promote rule: cost ≤ 0.7 and
  occurrences ≥ 3). The divergence is the calibration set for going live.
- **Revalidation**: `gemini-3.5-flash-lite → gemini-3.6-flash` moves **5/5
  probes** → `revalidation_failed`, auto-demote to trial; `gemini-3.6-flash →
  gemini-3.8-flash` moves 5/5 as well (2026-09-10, one run each). Deliberately
  conservative: a *better* model demotes too, because the fingerprint is a
  change detector, not a quality detector. Only extracted **text** is hashed, so
  proof does not expire on volatile response metadata.
- **Silence-demotion**: a shadow rule, **data-injected**: the runtime does not
  yet track last-solicitation. The loop is not closed in v1.

---
