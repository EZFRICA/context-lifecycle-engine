# CLE Metrics, Fixture Eras

Every number the system produces on **fixtures**, with its provenance and the
test that pins it. Numbers measured on real corpora are in `docs/FINDINGS.md`;
the contract is `docs/BLUEPRINT.md`.

Written across three measurement runs, and **later runs invalidated earlier
numbers**. Read the era label before the figure.

| Era | Data | Embedder | Status |
|---|---|---|---|
| **A, legacy demo** | templated `make_fixture.py` | `stub:hashed64` @0.6 | still shipped as the demo; **not realistic usage** |
| **B, realistic data** | realistic freeze-once fixtures | `stub:hashed64` @0.6 | superseded for detection numbers |
| **C, real embedder** | same realistic fixtures | `google:gemini-embedding-2:768` @0.775 | **current** |

* **Where A/B and C disagree, C wins.**
* Numbers labelled by agent name are **era A**, on a templated source. Demo
  mechanics, not measured reality.
* A number with no era and no test name should be distrusted.

Suite: **394 tests across 42 files**, `python -m pytest -q`. Five more run only where the private WildChat corpus is present, so they are not counted here: a suite size a reader cannot reproduce is not a suite size. See
`docs/TESTING.md`.

---
## Two headline findings

### 1. v1 detection only worked because the data was templated

The original fixtures repeated one identical opener per intent (the string
`"schedule the monthly gdg meetup in the main room"` appeared 45 times, once
per day, a *monthly* meetup scheduled daily). Rebuilt with genuinely varied
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

### 2. A real embedding model is not a drop-in, and it breaks contradiction detection

Swapping in `google:gemini-embedding-2:768` (frozen vectors, offline):

- at the **unchanged 0.6** threshold it fails the opposite way, **over-merging**
  everything into **2 clusters**, with `false_trigger` exploding
  **0.061 → 0.632** (events intent, ideal centroid);
- **recalibrated to 0.775** it genuinely beats v1, but GDG recovery still tops
  out at **2/7** planted intents, and of the 6 candidates it births only **2 are
  genuine** (see *Born-candidate purity*);
- it **breaks the contradiction classifier outright**: **zero divergent pairs**
  across all seven intents. Cosine measures *topical relatedness, not
  contradiction*, the planted **opposing** directives score **0.62–0.86**
  because they *are* about the same thing.

No threshold rescues the third point (the bar would have to exceed 0.86, which
flags every pair). It needs a different operator, signed / entailment, which
is its own run.

---

## Eras A and B, superseded

Detail in `docs/METRICS-ERAS-AB.md`. The short version, because era C only
makes sense against it:

* **Era A** (legacy templated demo): three clean agents, high capture, low false
  trigger. Those numbers came from `make_fixture.py` emitting templated text, not
  from detection working.
* **Era B** (realistic data, v1 embedder): the same detector on varied phrasing
  shattered every recurring intent into near singletons. Holdout discovery fell
  to **0**.

---

## Era C, the real embedder (current)

Substrate `google:gemini-embedding-2:768`, 768-dim MRL-truncated. **247 distinct
fixture texts** embedded in 247 calls (84.2 s) and frozen to
`examples/vectors.google-gemini-embedding-2-768.json`. CI reads them through
`CachedEmbedder`; a miss raises `CacheMissError` and never recomputes.

### Pinning key

Every figure below is a measurement, and a measurement without provenance is a
number. The embedding configuration has a key; so does every published
figure, which carries **(date, commit, embedder_id,
model_id)**.

| figure family | date | commit | embedder_id | model_id |
|---|---|---|---|---|
| threshold sweep, before/after table | 2026-07-24 | `19a0313`..`76efdc0` | `stub:hashed64` **and** `google:gemini-embedding-2:768` | n/a (no LLM on this path) |
| fingerprint determinism (3/3 distinct) | 2026-08-30 | `eca74ca` | n/a | `gemini-3.5-flash-lite` |
| Measure A (below) | 2026-08-30 | `eca74ca` + the tree that became this change | `stub:hashed64` / `google:gemini-embedding-2:768` | n/a |

**On the space of each figure.** The before/after table is already
space-annotated by its column headers, `v1 @0.6` is `stub:hashed64`, `real @…`
is `google:gemini-embedding-2:768`. So `capture 0.50 → 0.81` and
`false_trigger 0.0614 → 0.6316` are **cross-space** comparisons at a fixed
threshold, not stub-space figures. `0.775` was calibrated in the real space.
Every figure was checked against its label; none needed re-labelling, only pinning.

**`gemini-3.5-flash-lite` is an alias, not a pinned version.** Any figure
carrying it measures the provider's routing as much as the substrate. Recorded
as a limitation of the fingerprint figures, not fixed here.

### Measure A, the detector on an independent fixture (offline, free)

Run on `prompt_history_gdg.jsonl` (516 texts, all 516 in the frozen cache), the
GDG generator being one of the two declared independent of the detector. 246
episodes, 10 thread-prefix classes.

| space | threshold | clusters | purity | pure ≥80% | classes recovered |
|---|---|---|---|---|---|
| `stub:hashed64` | 0.6 | 63 | 0.882 | 53/63 | 9/10 |
| `google:gemini-embedding-2:768` | 0.775 | 40 | 0.935 | 36/40 | 9/10 |

**Three reservations, in the text and not in a footnote:**

1. **One threshold per space, not a curve.** Cluster count and purity are
   *jointly* determined by the threshold, so a single point cannot separate the
   effect of the space from the effect of the threshold. The result runs
   *against* the confound's expected direction (a higher threshold yielding
   *fewer* clusters), so it holds, but "better on every axis" is attached to
   "at this threshold" and does not travel without it.
2. **40 clusters for 10 classes is 4× over-fragmentation, in both spaces.** The
   real space fragments less (40 vs 63), not little. This table must not be read
   as "detection works".
3. **The missed class is `abandon`, identically in both spaces**: so it is a
   property of the data (abandoned episodes have no coherent opener), not
   information about the geometry.

**A separate script reproduces the PIPELINE, not the result:** 63 clusters under the stub and 40
under the real space at 0.775 match the before/after table above exactly, from a
script written months later. That establishes the published numbers are not
transcription errors, useful, and no more. It calls the same clusterer, so it
says nothing about whether the clustering is correct. The recovery figures do **not** compare -
this table's "classes" are thread-prefix classes at ≥80% purity, the older
table's are strict/lax recovery over 7 planted intents. Different definitions;
do not read 9/10 against 2/7.

### Before / after (GDG, 246 episodes)

| figure | v1 @0.6 | real @0.6 | real @0.775 |
|---|---|---|---|
| detected clusters | 63 | **2** | 40 |
| intents recovered (strict) | 0/7 | 0/7 | **2/7** |
| intents recovered (lax) | 1/7 | 0/7 | **4/7** |
| clusters reaching ≥3 gate | 22 | 2 |, |
| events capture (ideal centroid) | 0.5000 | 0.8106 | 1.0000 |
| events false_trigger | 0.0614 | **0.6316** | 0.0044 |
| events historical_cost | 2.4375 | 2.1322 |, |
| holdout discovery | 0 | 1 *(spurious)* | **3** |

### Threshold sweep, a clean inverted U

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

Below ~0.70 purity collapses (recall ~1.0, purity ~0.0, everything merges);
above ~0.85 recall collapses (purity 1.0, recall 0.1–0.3, fragmentation).

**Adopted: 0.6 → 0.775**, scoped to `embedder_id` (0.6 stays correct for
`stub:hashed64`); `CLUSTER_THRESHOLD_BY_EMBEDDER` in `cle/detect/clusters.py`.

> **What that 0.775 actually rests on.** The GDG sweep peak is **in-sample** -
> 0.775 was *chosen* on the fixture it is then scored against, so the 2/7 is not
> independent evidence. The credible support is the **holdout**:
> process-independent, authored without knowledge of the embedder, and never
> consulted to pick the threshold. That is **a single independent confirmation
> point**: one holdout, one threshold, one embedder. It justifies adopting
> 0.775 over 0.6; it does not establish 0.775 as calibrated in general.
> *Now pinned by `test_holdout_discovery.py::test_holdout_discovery_on_the_default_embedder`.*

### Born-candidate purity, counts NEVER stand bare

A bare count is the trap (cf. the holdout's spurious 0→1). Classification:
**GENUINE** = recall ≥0.8 and purity ≥0.8; **FRAGMENT** = purity ≥0.8, recall
<0.8 (a pure subset); **SPURIOUS** = purity <0.8 or no planted intent.

| fixture | born | GENUINE | FRAGMENT | SPURIOUS |
|---|---|---|---|---|
| GDG | 6 | **2**: `speakers` r0.92/p1.00, `agenda_workshop` r0.89/p1.00 | 2, `newsletter` r0.19/p1.00, `sponsors` r0.64/p0.90 | 2, a 20-episode agglomerate merging events+agenda_meetup+venue_policy (p0.45); a 3-episode noise recurrence (no intent) |
| holdout | 3 | **2**: `outreach` r0.89/p0.89, `meetup-prep` r0.89/p1.00 | 1, `venue` r0.56/p1.00 | 0 |

So the honest reading of "6 GDG candidates" is **2 genuine, 2 pure fragments, 2
spurious**: and both spurious ones would reach a human as proposals. That is
precisely why the disclosed-gap marker exists on the Births card. GDG's 2
genuine matches the sweep's 2/7 strict.

Note the holdout wording: earlier drafts said it "recovers 3/3". That
overstated it, 8/9, 8/8, 5/5 are **purity**; under recall *and* purity it is
**2 clean + 1 pure fragment**.

Also note what the holdout companion test does NOT report: it drives the
**ungated** `detect_signal`, so no stability check runs and the `Signal.stability`
it prints is an unexamined default (`stable`), not a measurement. It must not be
read against the `unavailable` verdict below, different code path, not a
contradiction.

### Downstream consumers under the real embedder

Detail in `docs/METRICS-ERAS-AB.md`. Two consumers are affected and the
direction differs:

* **Contradiction classification goes fully blind.** Cosine measures topical
  relatedness, not contradiction, so the four type taxonomy detects nothing in a
  semantic space. The classifier reports `unavailable`, which is a disclosed
  gap, never a reassuring "stable".
* **`world_state` is superseded, not answered.** The question it was posed to
  settle stopped being the right question.

### What got WORSE

1. **Contradiction detection: from partial to none.** The whole four-type
   taxonomy is inert under a semantic embedder.
2. **`false_trigger` at the unchanged threshold: 0.061 → 0.632** (10×; events
   intent, ideal centroid).
3. **Over-merging replaces over-fragmenting**: and hides better, because
   `capture` *rises* (0.50 → 0.81) while the trigger steals most out-of-cluster
   traffic.
4. **Holdout 0 → 1 at 0.6 is spuriously non-zero** (a single noise-dominated
   mega-cluster, purity 14/41), a number that looks like progress and is not.
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
| **ground truth** (`make_gdg_fixture.py`) | **recovery**: planted patterns must come back | realistic (era B/C) |
| **adversarial** (`make_fixture.py`) | **rejection**: a bridge fires, traps do not | **still templated** (era A) |
| **holdout** (`make_holdout.py`) | **discovery**: unplanted patterns emerge | realistic; imports **nothing** from `cle` |

The holdout is the only one authored without knowledge of the embedder geometry,
the cosine threshold, or any centroid. That is what makes it the confirmation
point above.

**Anti-templating guard** (`test_fixture_realism.py`): asserts **data**
properties grouped by planted intent (≥8 distinct openers per recurring intent,
no sentence >15% of messages, timing not single-valued), so a fixture regressing
to templated text fails the suite instead of being found three runs later.

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
  are a **constructed window** with a **deliberately planted** bridge, engineered
  to show the machinery fires, not an emergent result.

---

## Known debt

- **De-template `make_fixture.py`** (and with it `full_loop.sh`, the four agent
  YAMLs, the dashboard demo). It is the live-demo backbone and is excluded from
  the realism guard.
- **A contradiction operator that is not a distance** (signed / entailment); until then the taxonomy is inert outside `stub:hashed64`.
- **A second independent confirmation** for the 0.775 threshold.
- **Fixture debt**: all four labelled `intra_cluster` contradictions live in the
  tool-**less** newsletter cluster, but world_state masking can only occur on a
  tool-**bearing** one, so the fixture never exercised the case the classifier
  was built for.
