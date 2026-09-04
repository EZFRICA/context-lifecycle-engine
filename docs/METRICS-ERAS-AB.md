# CLE Metrics, Eras A and B

The superseded measurement eras, kept because the current numbers are only
legible against what they replaced.

* **Era A**: the legacy templated demo. Clean results that came from templated
  fixtures, not from the detector working.
* **Era B**: realistic data on the v1 bag of tokens embedder. Where era A's
  results fell apart.

Era C, the current one, is in `docs/METRICS.md`. Measurements on real corpora are
in `docs/FINDINGS.md`.

---

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
  probes** → `revalidation_failed`, auto-demote to trial. Deliberately
  conservative: a *better* model demotes too, because the fingerprint is a
  change detector, not a quality detector. Only extracted **text** is hashed, so
  proof does not expire on volatile response metadata.
- **Silence-demotion**: a shadow rule, **data-injected**: the runtime does not
  yet track last-solicitation. The loop is not closed in v1.

---

## Era B, realistic data, v1 embedder

Fixtures: freeze-once, generated once and **committed** (determinism comes from
the artifact, not from a deterministic generator). GDG ground truth: 516
messages, 246 episodes, 112 days, one francophone GDG Abidjan organiser.

### Detector recovery (grouped by *planted* intent, never by detected cluster)

| planted intent | occurrences | distinct openers | detected clusters |
|---|---|---|---|
| events | 10 | 10 | 9 |
| newsletter | 16 | 12 | 11 |
| speakers | 12 | 12 | 11 |
| sponsors | 14 | 12 | 10 |
| agenda_meetup | 9 | 8 | 6 |
| agenda_workshop | 9 | 8 | 4 |
| venue_policy | 8 | 8 | 8 |

63 clusters total; 22 reach the ≥3-occurrence signal gate, none mapping cleanly
to a planted intent. Under a strict criterion (one cluster holding ≥80% of an
intent **and** ≥80% pure), v1 recovers **0/7**: and that is its *best across a
full 0.40–1.10 sweep*, not just at 0.6. Lax (≥50%/≥50%): 1/7.

### Stability per planted intent

| intent | unstable | resolution | band_width | ws_share_pct | ws_would_be_intra |
|---|---|---|---|---|---|
| events (tool) | True | resolved | 0.3381 | 35.5 | 2 |
| newsletter | True | resolved | 0.3474 | 0 | 0 |
| speakers (tool) | True | resolved | 0.2691 | 0 | 0 |
| sponsors (tool) | True | resolved | 0.3464 | 0 | 0 |
| agenda_meetup | True | resolved | 0.1760 | 0 | 0 |
| venue_policy | True | resolved | 0.3354 | 0 | 0 |

The degenerate `band_width = 0.0000` of the templated era was purely an
artifact. But note the **over-flag** side: with realistic follow-up variety the
classifier reads lexical spread as "divergence", so `venue_policy`'s genuine
temporal evolution is flagged unstable and its candidate suppressed. The same
embedder limitation, one layer down.

### Replay & discovery

- `events` planted-centroid (the **ideal** trigger): `capture = 0.500`,
  `false_trigger = 0.0614`, `historical_cost = 2.4375`. Even the mean of all
  its own openers matches only half of them at 0.6.
- **Holdout discovery: 0** (109 messages, 41 episodes). Each recurring pattern
  (`meetup-prep`, `outreach`, `venue`, 9 occurrences each) fragments into 8–9
  clusters, none reaching the gate.

---


---

# Downstream consumers under the real embedder (era C detail)

### Consumer 2, stability / contradiction goes fully blind

| figure | v1 | real |
|---|---|---|
| divergent pairs, all 7 intents | many | **0** |
| events band_width | 0.3381 | 0.0000 |
| events ws_share_pct | 35.5 | 0.0 |
| events intra_cluster pairs | 3 | 0 |
| every intent `unstable` | True | False (all) |

Planted **opposing** directive cosines, real vs stub:

| pair | real (min/mean/max) | below 0.35 | stub (mean) | below 0.35 |
|---|---|---|---|---|
| newsletter short↔long | 0.619 / 0.657 / 0.699 | **0/4** | 0.251 | 3/4 |
| venue diy↔ask-approval | 0.666 / 0.739 / 0.864 | **0/12** | 0.239 | 10/12 |
| events confirm↔reroute | 0.657 / 0.676 / 0.693 | **0/4** | 0.138 | 4/4 |

**This is the wrong operator, not a mis-set threshold.** v1 only appeared to
detect contradictions by accident: opposing instructions happen to use
different *words*, so lexical overlap was low. `venue_policy`'s over-flag from
era B disappears, but for the wrong reason: nothing is flagged at all.

Because the check is unsound here it returns `verdict="unavailable"`, which
does **not** block birth (BLUEPRINT §5b). Reversing an earlier block restored
the first pillar from **0** candidates to 6 (GDG) / 3 (holdout).

### `world_state`: the question is superseded, not answered

Injecting the same moderate contradiction into the tool-bearing `events` intent:

| embedder | directive cosine | classified as | cluster after injection |
|---|---|---|---|
| stub (v1) | 0.1140 | `world_state` (absorbed) | unstable=True, intra=3 |
| real | **0.7197** | **not divergent at all** | unstable=False, intra=0 |

Under v1 the narrow rule-level blindness was real (a moderate flip co-occurring
with a differing `tool_result` got absorbed). Under the real embedder the pair
never registers as divergent, so it never reaches the rule: **the rule is
unreachable, not fixed**. v1 at least saw divergence and mis-attributed some of
it; the real embedder sees none.


---

# Two traps in building the vector cache

Both are silent, both are now guarded, and both are worth knowing before
regenerating the cache.

1. **A list of contents is ONE document, not a batch.** `gemini-embedding-2`
   treats `contents=[...]` as a single multi-part document and returns a single
   embedding, so 190 texts come back as 2 vectors with nothing raised. The only
   visible symptom is file size: 34 KB where ~3 MB was expected. Embed one
   content per call (190 calls, 62.7 s). Guarded by
   `test_vector_cache_has_one_distinct_vector_per_text`, which asserts the count
   matches the texts and that no two distinct texts share a vector.
2. **Two consumers embed two SHAPES of text.** Clustering and replay embed an
   opener; the stability classifier embeds the follow-ups **joined** into one
   string, which is no single message. A cache covering only message texts
   raises `CacheMissError` part way through a run. For the shipped fixtures that
   is the difference between 190 and 247 vectors.

---

