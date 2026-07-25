# CLE Metrics Inventory — Article 9 Skeleton

Every number the system produces, with its provenance, its honest scope, and
the test that pins it. Suite: **220 tests across 26 files** (+1 opt-in
integration test, skipped by default) — `uv run pytest`.

The contract is `docs/BLUEPRINT.md`; this document is measurement only. Where
the two disagree, that is a finding to raise, not a doc to quietly edit.

---

## How to read this document

It was written across three measurement runs, and **later runs invalidated
earlier numbers**. Read the era label before the figure. Three eras:

| Era | Data | Embedder | Status |
|---|---|---|---|
| **A — legacy demo** | templated `make_fixture.py` | `stub:hashed64` @0.6 | still shipped as the demo; **not realistic usage** |
| **B — realistic data** | realistic freeze-once fixtures | `stub:hashed64` @0.6 | superseded for detection numbers |
| **C — real embedder** | same realistic fixtures | `google:gemini-embedding-2:768` @0.775 | **current** |

Rules for the reader:

- **Where A/B and C disagree, C wins.**
- Numbers labelled by agent name (`weekly_recap` 0.60, the recap-family 0.081,
  the three detected agents) are **era A**. That source is still templated;
  treat them as demo mechanics, not measured reality.
- Anything not re-measured in era C carries its era inline.
- If a number has no era and no test name, distrust it.

---

## Two headline findings

### 1. v1 detection only worked because the data was templated

The original fixtures repeated one identical opener per intent (the string
`"schedule the monthly gdg meetup in the main room"` appeared 45 times, once
per day — a *monthly* meetup scheduled daily). Rebuilt with genuinely varied
human phrasing (≥ 8 distinct openers per recurring intent, franglais, typos,
irregular timing), the same detector:

- **shattered every planted intent**: `events` 10 distinct openers → 9 clusters,
  `venue_policy` 8 → 8; **63 clusters for 7 planted intents**;
- **discovered nothing** on the process-independent holdout: **0 agents**
  (the templated holdout had yielded 2 of 3);
- revealed its clean metrics as artifacts: the tool-bearing `events` directive
  band went `0.0000 → 0.3381`, `ws_share_pct` `100% → 35.5%`, and the "perfect"
  `capture = 1.000` became **0.500** *even from the ideal centroid*.

Identical openers are the one input a 0.6 bag-of-tokens embedder clusters
reliably. This is a finding about the **detector**, not the data: no threshold
was tuned to soften it.

### 2. A real embedding model is not a drop-in — and it breaks contradiction detection

Swapping in `google:gemini-embedding-2:768` (frozen vectors, offline):

- at the **unchanged 0.6** threshold it fails the opposite way — **over-merging**
  everything into **2 clusters**, with `false_trigger` exploding
  **0.061 → 0.632** (events intent, ideal centroid);
- **recalibrated to 0.775** it genuinely beats v1 — but GDG recovery still tops
  out at **2/7** planted intents, and of the 6 candidates it births only **2 are
  genuine** (see *Born-candidate purity*);
- it **breaks the contradiction classifier outright**: **zero divergent pairs**
  across all seven intents. Cosine measures *topical relatedness, not
  contradiction* — the planted **opposing** directives score **0.62–0.86**
  because they *are* about the same thing.

No threshold rescues the third point (the bar would have to exceed 0.86, which
flags every pair). It needs a different operator — signed / entailment — which
is its own run.

---

## Era A — the legacy templated demo (`examples/full_loop.sh`)

Produced by `make_fixture.py`, which has **not** been de-templated. These
numbers describe *mechanics* and are reproducible offline (`CLE_MODEL_A/B=stub-*`).

### Build

| Metric | Value | Source & scope |
|---|---|---|
| `capture_rate` | `weekly_recap` **0.60**, others 1.00 | `cle/build/replay.py`. 0.60 because the hand-authored `status_report` incumbent already owns 2 of its 5 reworded episodes — capture is measured **against the current topology**, not in a vacuum. |
| `false_trigger_rate` | **≈ 0.081** (recap family), 0.0 others | Out-of-cluster episodes the trigger would steal. The adversarial window plants one firing "bridge" + 4 near-miss traps that are correctly rejected (0.091 with the bridge alone → 0.081 once the traps enlarge the denominator). |
| `historical_cost` | recap 3.4, standup 2.7, incident 7.0 it/ep | Mean iterations of in-cluster episodes, **abandoned excluded** (anti-Goodhart: an agent that induces abandonment must not profit from fewer counted iterations). |
| `closure_distribution` | per-agent success/reformulated/abandoned | One op line per successful replay. |

*Pinned by* `test_replay.py` (both rates always computed, determinism,
competition lowers capture), `test_adversarial_fixture.py` (non-zero false
trigger). **Era-A caveat**: the bridge fires because it *shares tokens*, not
because it is semantically close.

### Runtime

- **Switch cost** `diff_blocks` **4** / `diff_tokens` **127** — symmetric
  difference of resolved block hashes on a real `weekly_recap → incident_triage`
  swap (disjoint component sets). *`test_runtime.py::test_ensure_run_and_switch_with_costs`.*
- **Per-container metrics** — one image, two workspaces, genuinely divergent
  counts; written one-way through `MetricsVolume.record()`. The container has
  **no read path** to them. *`test_goodhart_boundary.py` (5 reflection tests).*

### Lifecycle

- **Shadow divergence** — human promotes `standup_digest` to `ephemeral` on
  `cost_ratio 0.95`; the engine logs `would: hold` (promote rule: cost ≤ 0.7 and
  occurrences ≥ 3). The divergence is the calibration set for going live.
- **Revalidation** — `gemini-3.5-flash-lite → gemini-3.6-flash` moves **5/5
  probes** → `revalidation_failed`, auto-demote to trial. Deliberately
  conservative: a *better* model demotes too, because the fingerprint is a
  change detector, not a quality detector. Only extracted **text** is hashed, so
  proof does not expire on volatile response metadata.
- **Silence-demotion** — a shadow rule, **data-injected**: the runtime does not
  yet track last-solicitation. The loop is not closed in v1.

---

## Era B — realistic data, v1 embedder

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
intent **and** ≥80% pure), v1 recovers **0/7** — and that is its *best across a
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

## Era C — the real embedder (current)

Substrate `google:gemini-embedding-2:768`, 768-dim MRL-truncated. **247 distinct
fixture texts** embedded in 247 calls (84.2 s) and frozen to
`examples/vectors.google-gemini-embedding-2-768.json`. CI reads them through
`CachedEmbedder`; a miss raises `CacheMissError` and never recomputes.

### Before / after (GDG, 246 episodes)

| figure | v1 @0.6 | real @0.6 | real @0.775 |
|---|---|---|---|
| detected clusters | 63 | **2** | 40 |
| intents recovered (strict) | 0/7 | 0/7 | **2/7** |
| intents recovered (lax) | 1/7 | 0/7 | **4/7** |
| clusters reaching ≥3 gate | 22 | 2 | — |
| events capture (ideal centroid) | 0.5000 | 0.8106 | 1.0000 |
| events false_trigger | 0.0614 | **0.6316** | 0.0044 |
| events historical_cost | 2.4375 | 2.1322 | — |
| holdout discovery | 0 | 1 *(spurious)* | **3** |

### Threshold sweep — a clean inverted U

| thr | clusters | recovered (strict) | events_false | events_capture |
|---|---|---|---|---|
| 0.600 | 2 | 0 | 0.6316 | 0.8106 |
| 0.650 | 3 | 0 | 0.0541 | 0.6699 |
| 0.700 | 13 | 1 | 0.2679 | 0.7051 |
| 0.750 | 33 | 1 | 0.0488 | 0.4634 |
| **0.775** | **40** | **2** | **0.0044** | **1.0000** |
| 0.800 | 51 | 1 | 0.0466 | 0.8000 |
| 0.850 | 80 | 0 | 0.0247 | 1.0000 |
| 0.900 | 91 | 0 | 0.0122 | 1.0000 |

Below ~0.70 purity collapses (recall ~1.0, purity ~0.0 — everything merges);
above ~0.85 recall collapses (purity 1.0, recall 0.1–0.3 — fragmentation).

**Adopted: 0.6 → 0.775**, scoped to `embedder_id` (0.6 stays correct for
`stub:hashed64`); `CLUSTER_THRESHOLD_BY_EMBEDDER` in `cle/detect/clusters.py`.

> **What that 0.775 actually rests on.** The GDG sweep peak is **in-sample** —
> 0.775 was *chosen* on the fixture it is then scored against, so the 2/7 is not
> independent evidence. The credible support is the **holdout**:
> process-independent, authored without knowledge of the embedder, and never
> consulted to pick the threshold. That is **a single independent confirmation
> point** — one holdout, one threshold, one embedder. It justifies adopting
> 0.775 over 0.6; it does not establish 0.775 as calibrated in general.
> *Now pinned by `test_holdout_discovery.py::test_holdout_discovery_on_the_default_embedder`.*

### Born-candidate purity — counts NEVER stand bare

A bare count is the trap (cf. the holdout's spurious 0→1). Classification:
**GENUINE** = recall ≥0.8 and purity ≥0.8; **FRAGMENT** = purity ≥0.8, recall
<0.8 (a pure subset); **SPURIOUS** = purity <0.8 or no planted intent.

| fixture | born | GENUINE | FRAGMENT | SPURIOUS |
|---|---|---|---|---|
| GDG | 6 | **2** — `speakers` r0.92/p1.00, `agenda_workshop` r0.89/p1.00 | 2 — `newsletter` r0.19/p1.00, `sponsors` r0.64/p0.90 | 2 — a 20-episode agglomerate merging events+agenda_meetup+venue_policy (p0.45); a 3-episode noise recurrence (no intent) |
| holdout | 3 | **2** — `outreach` r0.89/p0.89, `meetup-prep` r0.89/p1.00 | 1 — `venue` r0.56/p1.00 | 0 |

So the honest reading of "6 GDG candidates" is **2 genuine, 2 pure fragments, 2
spurious** — and both spurious ones would reach a human as proposals. That is
precisely why the disclosed-gap marker exists on the Births card. GDG's 2
genuine matches the sweep's 2/7 strict.

Note the holdout wording: earlier drafts said it "recovers 3/3". That
overstated it — 8/9, 8/8, 5/5 are **purity**; under recall *and* purity it is
**2 clean + 1 pure fragment**.

Also note what the holdout companion test does NOT report: it drives the
**ungated** `detect_signal`, so no stability check runs and the `Signal.stability`
it prints is an unexamined default (`stable`), not a measurement. It must not be
read against the `unavailable` verdict below — different code path, not a
contradiction.

### Consumer 2 — stability / contradiction goes fully blind

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
era B disappears — but for the wrong reason: nothing is flagged at all.

Because the check is unsound here it returns `verdict="unavailable"`, which
does **not** block birth (BLUEPRINT §5b). Reversing an earlier block restored
the first pillar from **0** candidates to 6 (GDG) / 3 (holdout).

### `world_state` — the question is superseded, not answered

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

### What got WORSE

1. **Contradiction detection: from partial to none.** The whole four-type
   taxonomy is inert under a semantic embedder.
2. **`false_trigger` at the unchanged threshold: 0.061 → 0.632** (10×; events
   intent, ideal centroid).
3. **Over-merging replaces over-fragmenting** — and hides better, because
   `capture` *rises* (0.50 → 0.81) while the trigger steals most out-of-cluster
   traffic.
4. **Holdout 0 → 1 at 0.6 is spuriously non-zero** (a single noise-dominated
   mega-cluster, purity 14/41) — a number that looks like progress and is not.
5. **`venue_policy`'s over-flag "fix" is illusory.**
6. **A new calibration coupling**: the threshold is now embedder-specific and
   must be versioned with `embedder_id`, or centroids and thresholds silently
   disagree.

---

## Three data sources, three roles

Evaluating a detector on data generated with that detector's own geometry is a
consistency check, not a discovery test. So:

| Source | Role | Status |
|---|---|---|
| **ground truth** (`make_gdg_fixture.py`) | **recovery** — planted patterns must come back | realistic (era B/C) |
| **adversarial** (`make_fixture.py`) | **rejection** — a bridge fires, traps do not | **still templated** (era A) |
| **holdout** (`make_holdout.py`) | **discovery** — unplanted patterns emerge | realistic; imports **nothing** from `cle` |

The holdout is the only one authored without knowledge of the embedder
geometry, the cosine threshold, or any centroid — which is what makes it the
confirmation point above.

**Anti-templating guard** (`test_fixture_realism.py`): asserts **data**
properties grouped by planted intent — ≥8 distinct openers per recurring
intent, no sentence >15% of messages, timing and turn-gaps not single-valued.
A fixture regressing to templated text fails the suite instead of being
discovered three runs later.

---

## Process failures in these runs (kept, with their retries)

Both were caught by luck rather than by a check; both are now guarded.

1. **The vector generation silently collapsed 190 texts into 2 vectors.**
   `gemini-embedding-2` treats a list of `contents` as ONE multi-part document,
   not a batch. Nothing raised — it was caught by eyeballing a 34 KB file that
   should have been ~3 MB. *Retry*: one content per call (190 calls, 62.7 s).
   *Now guarded*: `test_vector_cache_has_one_distinct_vector_per_text` asserts
   count-matches-texts and that no two distinct texts share a vector.
2. **The cache-coverage decision was incomplete.** Two consumers embed two
   *shapes* of text: clustering/replay embed an opener, but the stability
   classifier embeds the follow-ups **joined** into one string, which is no
   single message. Covering only message texts would have raised
   `CacheMissError` mid-run. *Retry*: cache 190 → 247 vectors.

---

## Honest caveats (apply to every number above)

- Replay tests the **trigger only**, never answer quality, and never the
  temporal period (`period_tested: false`).
- A fingerprint delta proves the **substrate changed**, not that the agent is
  broken.
- `capture_rate` is relative to the **current topology**, not an absolute.
- **Silence-demotion** is data-injected in v1; the loop is not closed.
- Demo closures are **synthetic** CLI sugar; real closures come from the detector.
- The **adversarial/demo source is still templated**, so every era-A number
  inherits that bias.
- `examples/gdg_demo.py`'s 1.000 → 0.600 competition and its 0.143 false-trigger
  are a **constructed window** with a **deliberately planted** bridge —
  engineered to show the machinery fires, not an emergent result.

---

## Known debt

- **De-template `make_fixture.py`** (and with it `full_loop.sh`, the four agent
  YAMLs, the dashboard demo). It is the live-demo backbone and is excluded from
  the realism guard.
- **A contradiction operator that is not a distance** (signed / entailment).
  Until then the taxonomy is inert outside `stub:hashed64`.
- **A second independent confirmation** for the 0.775 threshold.
- **Fixture debt**: all four labelled `intra_cluster` contradictions live in the
  tool-**less** newsletter cluster, but world_state masking can only occur on a
  tool-**bearing** one — so the fixture never exercised the case the classifier
  was built for.
