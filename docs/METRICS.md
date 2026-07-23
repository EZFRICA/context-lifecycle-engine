# CLE Metrics Inventory — Article 9 Skeleton

Every number `examples/full_loop.sh` produces, with its provenance, honest
scope, and the **test that pins it**. The suite has **204 tests (+1 opt-in integration) across 26 files**
(`uv run pytest`); each metric below names the test(s) that guard its
behaviour.

## HEADLINE FINDING (realism run) — v1 detection worked only because the data was templated

The old fixtures were templated: one identical opener repeated per intent
(`"schedule the monthly gdg meetup in the main room"` appeared 45 times, once
per day). The realism run replaced them with genuinely varied human usage
(≥ 8 distinct phrasings per recurring intent, franglais, typos, irregular
timing; `examples/phrasing.py`, frozen into the committed `.jsonl`). Re-running
detection on that realistic data is unambiguous:

- **The v1 bag-of-tokens embedder (cosine 0.6) cannot cluster paraphrase.**
  Each planted intent shatters into near one-cluster-per-episode: on the GDG
  ground-truth fixture `events` recovers as **10 openers → 9 clusters**,
  `venue_policy` **8 → 8**; 63 detected clusters for 7 planted intents.
- **Discovery collapses to zero.** The process-independent holdout, which the
  old templated version recovered 2 of 3 patterns from, now yields **0 agents
  discovered** — every recurring pattern fragments below the 3-occurrence
  signal gate.
- **The degenerate metrics were artifacts.** `band_width` on the tool-bearing
  `events` intent went **0.0000 → 0.3381**; `ws_share_pct` **100% → ~30%**;
  the "perfect" `capture=1.000` becomes **0.500** even from the *ideal*
  centroid (it cannot match its own varied openers).

The unavoidable conclusion, stated plainly: **v1 detection was only ever
"working" because the fixtures were templated.** Identical openers are the one
input a 0.6 bag-of-tokens embedder clusters reliably; realistic usage defeats
it. This is the most important result of the project so far. It is a finding
about the DETECTOR, not the data — no threshold was tuned to hide or soften it
(the realism-run decision: realistic data uncapped, guard on data properties
grouped by planted intent, recovery **reported not gated**). The embedder
upgrade (a char-n-gram / small-model swap behind the existing `Embedder`
Protocol) is the deliberately-separate next run, now measurable as a delta
against this frozen realistic baseline.

The full per-intent re-measurement is in *Realism run — re-measurement* below;
the anti-templating guard is `tests/unit/test_fixture_realism.py`.

> **Numbers vs. substrate.** The replay numbers (`capture_rate`,
> `false_trigger_rate`, `historical_cost`, `closure_distribution`) are computed
> from the **embedder + trigger geometry** and are identical whether the build
> runs on a real Gemini model or a stub — only the `model_fingerprint` depends
> on the model. So these numbers are reproducible offline even though the
> system runs on real models locally.

> **Caveat — the pre-realism numbers below.** The per-metric provenance in the
> sections that follow (e.g. `weekly_recap` capture 0.60, the recap-family
> false-trigger 0.081) is from `make_fixture.py`, the ADVERSARIAL/demo source
> that is still templated (see *Scope note* at the end). Treat those as the
> legacy-demo numbers; the realistic re-measurement is the *Realism run* section.

## Build metrics

### `capture_rate` — varies (e.g. `weekly_recap` 0.60, others 1.00)
- **Source**: `cle/build/replay.py` — fraction of the cluster's episodes whose
  opener the candidate's trigger would intercept, **measured against the current
  topology**: an incumbent whose centroid is closer wins the episode
  (`candidate_similarity > incumbent_similarity`, ties to the incumbent).
- **Why it's not always 1.0**: `weekly_recap` captures 0.60 because the
  hand-authored `status_report` already owns 2 of its 5 (reworded) episodes —
  capture is what the candidate would *actually* intercept, not what it could in
  a vacuum. Uncontested agents (`standup_digest`, `incident_triage`) capture 1.00.
- **Verified by**: `test_replay.py::test_both_rates_are_always_computed`,
  `::test_out_of_cluster_capture_shows_in_false_trigger_rate`,
  `::test_existing_topology_wins_ties_and_reduces_capture` (competition lowers
  capture); determinism by `::test_replay_is_deterministic`.
- **Does NOT prove**: answer quality (invariant 5 — trigger geometry only). See
  *Honest caveats* §3 for the period-not-tested note.

### `false_trigger_rate` — ≈ 0.081 for the recap family, 0.0 for the others
- **Source**: `cle/build/replay.py` — fraction of **out-of-cluster** episodes
  the candidate would have stolen. Always computed wherever `capture_rate` is.
  The adversarial window contains a "bridge" episode that *fires* (a genuine
  false trigger, keeping the rate off zero) plus several near-miss **traps**
  that are correctly *rejected* (they lower the rate by growing the correctly-
  handled out-of-cluster denominator — 0.091 with the bridge alone → 0.081 once
  the traps are added).
- **Verified by**: `test_replay.py::test_both_rates_are_always_computed`;
  `test_adversarial_fixture.py::test_adversarial_window_produces_false_triggers`
  (asserts the recap trigger yields a non-zero rate on the adversarial window).
- **Does NOT prove**: zero false triggers at deployment — the window is a
  sample; shifted traffic may route differently.

### `historical_cost` — per-agent (recap 3.4, standup 2.7, incident 7.0 it/ep)
- **Source**: `cle/build/replay.py` — mean iteration count of in-cluster
  episodes, **excluding abandoned** closures (anti-Goodhart: an agent that
  induces abandonment must not benefit from fewer counted iterations).
- **Verified by**: the abandoned-exclusion rule —
  `test_episodes.py::test_silent_expensive_close_is_abandoned` and
  `test_signals.py::test_baseline_is_median_iterations_excluding_abandoned`;
  the value ships in `PreEvidence` (`test_replay.py`).
- **Does NOT prove**: the candidate will lower cost — it's the baseline that
  trial `Evidence.cost_ratio` is later measured against.

### `closure_distribution` — success / reformulated / abandoned (per agent)
- **Source**: `cle/build/replay.py` — one op line per successful replay with
  per-label counts (e.g. `incident_triage` → reformulated-heavy).
- **Verified by**:
  `test_build_invariants.py::test_successful_build_logs_exactly_one_line_with_pre_evidence`
  (the `closure_distribution` line precedes the `build` line); classification by
  `test_episodes.py` (`test_marker_means_success`,
  `test_no_marker_but_return_is_reformulated`, `test_silent_cheap_close_is_success`,
  `test_silent_expensive_close_is_abandoned`).
- **Does NOT prove**: real closure quality — demo closures are labels derived
  from iteration counts; true closures need the detector watching for a return.

## Runtime metrics

### Switch cost: `diff_blocks` (4) / `diff_tokens` (127)
- **Source**: `cle/runtime/container.py::switch_cost()` — symmetric difference
  of resolved block hashes between outgoing and incoming images, plus the token
  count of the changed blocks. In the demo this is a *real* switch
  (`weekly_recap → incident_triage`, disjoint component sets).
- **Verified by**: `test_runtime.py::test_ensure_run_and_switch_with_costs`
  (asserts the `switch` line carries both `diff_blocks` and `diff_tokens`, and
  that they equal `switch_cost()`).
- **Does NOT prove**: cognitive switch cost for the user — it's the context
  delta the system must load, a lower bound on disruption.

### Per-container metrics (solicitations, iterations, closures)
- **Source**: `cle/runtime/metrics_volume.py` — one-way writes via
  `MetricsVolume.record()`; read only by `cle ps` / the dashboard (the container
  has **no** read path to its own metrics — the Goodhart boundary).
- **Verified by**:
  `test_runtime.py::test_metrics_volume_is_write_only_and_readable_from_the_other_side`,
  `::test_solicit_writes_no_store_objects`, and the five
  `test_goodhart_boundary.py` reflection tests (the `Container` record exposes no
  metrics surface).
- **Does NOT prove**: agent quality — divergent counts prove isolation works,
  not that one workspace is better served.

## Lifecycle metrics

### Shadow-engine divergence (human vs. engine `would:`)
- **Source**: `cle/lifecycle/engine.py::shadow_decide()` — every `cle tag` with
  evidence also runs the engine in shadow; the line carries
  `actor:"engine:shadow"` and `would:"<decision>"`. The demo shows a real
  divergence: human `→ ephemeral`, engine `would: hold` (cost 0.95 > the 0.7
  promote threshold).
- **Verified by**:
  `test_lifecycle.py::test_shadow_engine_decides_but_never_writes` (promote /
  pin / demote / archive / hold decisions, and that the store snapshot is
  unchanged — shadow never writes).
- **Does NOT prove**: the engine is ready for live mode — agreement on demo
  data is trivial; the divergences are the v2 calibration set.

### Silence-based demotion (`would: demote_silence`)
- **Source**: `cle/lifecycle/engine.py` — fires when
  `days_since_last_solicitation > silence_factor × trigger_period_days` (2.0×).
- **Verified by**: `test_lifecycle.py::test_shadow_engine_silence_demotion`.
- **Scope (v1)**: shadow rule, data-injected in v1 — the runtime does not yet
  track last-solicitation; wiring it into `metrics_volume` is the v2 step. The
  rule fires correctly when the caller supplies the data; no v1 code path closes
  the loop automatically.

### Revalidation: `probe_deltas` (5/5 probes moved)
- **Source**: `cle/lifecycle/revalidator.py` — replays the image's frozen
  probe set and compares per-probe output hashes (frozen at build in
  `Image.probe_output_hashes`) to fresh ones; drift is **localized** —
  `probe_deltas` names which probes moved.
- **Real-substrate behaviour (verified live)**: at temperature 0 the same model
  yields the same fingerprint (`proof holds`); a *different* real model
  (`gemini-3.5-flash-lite` → `gemini-3.6-flash`) moves 5/5 probes
  (`proof expires` → auto-demote to trial). Only the extracted **text** is
  hashed — volatile response metadata is stripped so proof doesn't expire on
  noise (`cle/build/fingerprinter.py::response_text`).
- **Verified by**: `test_lifecycle.py::test_revalidate_holds_then_drifts`
  (same model holds, changed model demotes and logs `revalidation_failed`).
- **Deliberate conservatism, not a validation.** The fingerprint is a change
  detector, not a quality detector. A *better* model — one whose outputs differ
  from the build-time probe answers — triggers demotion just as a degraded one
  would. This is intentional: the CLE cannot distinguish improvement from
  regression without running the agent on live traffic. Re-earning evidence under
  the new substrate is the designed cost, not a bug. "5/5 probes moved" means
  the substrate changed; it says nothing about whether the change was good or
  bad.

## Topology metrics

### `diff_size` (0 or 1 per `topology_write`)
- **Source**: `cle/lifecycle/topology.py::write_topology()` — 1 if the durable
  entry (state + image + cause) changed, 0 if only the timestamp moved.
- **Verified by**: `test_lifecycle.py::test_topology_chain_diff_and_log`
  (version chaining, structured diff, and the `render_log` provenance).
- **Does NOT prove**: anything alone — it's the building block for topology
  churn rate.

### Version chain (many versions across the full loop)
- **Source**: `cle/lifecycle/topology.py` — monotonic `topology/v<n>`, one per
  change, parent-chained. The loop walks births (4 agents), promotions, a
  demotion, drift, and the v2 rebuild, so the chain runs well past a dozen
  versions; `cle diff topology/v1 topology/v3` renders the three detected agents
  appearing.
- **Verified by**: `test_lifecycle.py::test_topology_chain_diff_and_log`.

---

## Three data sources, three roles

All replay numbers currently come from one of three history sources. Their
roles are distinct and non-interchangeable.

| Source | Generator | Role | What it tests |
|--------|-----------|------|---------------|
| **ground\_truth** | `examples/make_fixture.py` | Planted patterns | The system **recovers** what we know is there. Centroids, openers, and periods are chosen to form distinct clusters above the threshold. |
| **adversarial** | `examples/make_fixture.py` (`adversarial_history()`) | Near-but-distinct traps | The system does **not** fire on what isn't there. One "bridge" episode is engineered to sit near the `weekly_recap` centroid and *fire* (a genuine false trigger); several near-miss traps (same vocabulary, different intent — a board report, standup comedy, a wilting houseplant, home wifi latency) must be *rejected*. |
| **holdout** | `examples/make_holdout.py` | Independent discovery | The system **discovers** unplanted patterns. The generator never imports from `cle/detect`, never reads the cosine threshold or centroids, and uses a completely different domain (GDG organiser). |

### Which existing numbers come from which source

| Metric | Source |
|--------|--------|
| `capture_rate` (weekly\_recap = 0.60, others = 1.00) | ground\_truth |
| `false_trigger_rate` ≈ 0.081 (recap family; bridge fires, 4 traps rejected) | adversarial |
| `historical_cost` (recap 3.4, standup 2.7, incident 7.0) | ground\_truth |
| `closure_distribution` per-agent | ground\_truth |
| `probe_deltas` (5/5 probes moved) | ground\_truth (build) + live substrate |
| Holdout: 2 agents discovered (recurrence ×6, reformulation ×4) | holdout |

### Holdout result (as discovered — not tuned)

The holdout history: **80 messages, 27 episodes, 85 days** (GDG organiser).
The detector found:

- `recurrence` signal: **6 occurrences, period = 14 days** (speaker outreach)
- `reformulation` signal: **4 occurrences** (venue coordination friction)

The monthly meetup prep (4 occurrences on a clean 28-day cadence) produced **no
recurrence signal** — a genuine, instructive surprise. The reason is not the
occurrence gate (its cluster holds 5 episodes, above `min_signal_occurrences = 3`):
the hashed-token embedder pulled a *noise* episode ("review the draft budget for
the q2 gdg events" — shared `gdg`/`draft` tokens) into the meetup cluster, so its
inter-arrival intervals became irregular (`[10, 18, 28, 28]` days) and the
recurrence signal's period-stability check correctly rejected it. This is honest
evidence of clustering imprecision under a cheap embedder; report it, do not tune
the threshold or hand-separate the clusters to force the pattern through.

> [!NOTE]
> Holdout numbers MUST NOT be used to tune thresholds. If the numbers are
> ugly or surprising, that is informative. Fix the threshold only if a separate
> theoretical or empirical argument (independent of the holdout) demands it.

### Test that guards the holdout

`tests/unit/test_holdout_discovery.py::test_holdout_discovery_structural_sanity`

Runs the full detector on the holdout, then replays the strongest discovered
candidate to **report** its capture / false-trigger / historical-cost. Asserts
only structural sanity: ≥1 agent detected, cold-start gate cleared, valid
centroids, every log line valid JSON with an `op` field, and the *real*
`false_trigger_rate` below `FALSE_TRIGGER_CEILING = 0.50` (a loose bound, never
tuned). It does **not** assert exact metric values — asserting them would make
the holdout a known fixture. (Current run: 2 agents; strongest replay reports
capture 1.0, false-trigger 0.0, cost 3.0 — reported, not asserted.)

---

## Cross-cutting invariants (what makes the numbers trustworthy)

| Invariant | Guarantee | Verified by |
|---|---|---|
| Two hashes | `Image.hash != Source.hash`, tags attach to images only | `test_build_invariants.py::test_two_hash_inequality`, `test_tag_targets.py` (5 tests) |
| Build determinism | same source + components + substrate ⇒ same image hash | `test_build_invariants.py::test_build_determinism` |
| Probe-set hash coverage | `probe_set` + `probe_output_hashes` are covered by `Image.hash` | `test_build_invariants.py::test_probe_set_is_hash_covered_and_deterministically_selected`, `::test_image_hash_covers_probe_output_hashes` |
| Staged builds write nothing | a failed resolve/replay leaves the store byte-identical | `test_staged_failure.py` (3), `test_resolver.py` (5) |
| Integrity | corrupt component → abort, log, refetch, never inject | `test_integrity.py` (4), `test_resolver.py::test_corrupt_component_fails_resolve_and_fires_integrity_log` |
| Evidence type separation | PreEvidence/Persistence can't reach a promotion | `test_evidence_types.py` (6) |
| Goodhart boundary | `Container` exposes no metrics read path | `test_goodhart_boundary.py` (5) |
| Hashing canonicalization | sorted keys, no whitespace, UTF-8, sha256 | `test_content_hash.py` (6) |
| Detection thresholds | silence, clustering, signals — all relative to the user | `test_episodes.py` (19), `test_clustering.py` (6), `test_signals.py` (10) |

## Honest caveats (apply to all numbers above)

1. **Real models locally, stub for CI.** `cle build`/`run`/`revalidate` use a
   live Gemini model by default (`gemini-3.5-flash-lite`); the fingerprint runs
   at temperature 0. GitHub CI forces stub substrates
   (`CLE_MODEL_A/B=stub-model-*`) so it never calls a model — and the **test
   suite** uses stub fingerprinters internally, needing no key or network.
2. **Residual API nondeterminism.** Even at temperature 0 a hosted model can
   occasionally return different text; that reads as a small genuine drift, not
   a bug. The `response_text` extractor removes volatile *metadata* drift, not
   real output drift.
3. **Period not tested by replay.** `PreEvidence.period_tested` is always
   `false`. Replay validates the **semantic trigger** (cosine against the
   centroid); the temporal period, when present, is carried into the image
   untested. Evaluating temporal fit retrospectively requires the v2 scheduler
   model. A `capture_rate` of 1.0 does not mean the period fires at the right
   time — it means the trigger geometry captures the right episodes.
4. **Silence-demotion: shadow rule, data-injected in v1.** The runtime does not
   yet track last-solicitation; wiring it into `metrics_volume` is the v2 step.
   The rule fires correctly when the caller supplies the data; no v1 code path
   closes the loop automatically.
5. **Demo closures are labels.** The offline stand-in and the iteration-count
   closure tags are deterministic sugar; real closures come from the detector
   observing a return to the cluster (v2).
6. **Single-user synthetic history.** Replay metrics from `make_fixture.py` are
   a consistency check (the system recovers planted patterns) and a false-trigger
   check (the adversarial bridge). A holdout source
   (`examples/make_holdout.py`) adds process-independent discovery. Real metrics
   need multi-user, multi-workspace deployment data.

## GDG enriched run — four-contradiction taxonomy (new)

Divergence inside a cluster is classified before synthesis
(`cle/detect/stability.py`; op line `cluster_stability`):

| Type | Rule | Reaction | Verified by |
|---|---|---|---|
| intra_cluster | opposing directives, gap <= 7d, same/no tool_result | UNSTABLE — no candidate | `test_contradictions.py` |
| grey_zone | gap in 7–21d (TOTAL partition — no uncovered interval) | UNSTABLE by default (calibratable band) | parametrized 3/12/30d |
| temporal | gap >= 21d | evolution; candidate from the post-flip segment | venue_policy fixture test |
| world_state | tool_result present BOTH sides and different, moderate divergence | environmental — NOT instability; candidate still born | make-or-break test |

Guards: no tool_result ⇒ never world_state (no external world in frame);
SEVERE divergence (<0.10) is never excused by a world change (adversarial
test) — the residual moderate-band mask is a documented, calibratable
limitation. Capability gating: capture = centroid match AND tool mount;
unmounted-tool episodes stay in the denominator. Tools are declarations
only — nothing is executed; `tool_result` is frozen decor, never asserted
correct. Backends: SqliteStore joins InMemory/File behind the same
Protocol (conformance parametrized ×3); Weaviate stays opt-in
(`integration` marker, skipped by default).

### `world_state_attribution` — the exclusion's reach, made permanent

The `cluster_stability` line now carries, on every analysis, how far the
world_state excuse reaches: `ws_would_be_intra` (world_state pairs that
would be `intra_cluster` by time alone — i.e. UNSTABLE with an identical
tool_result) and `ws_share_pct` (world_state / all divergent pairs). The
per-type counts moved under a `divergent_pairs` object so the log is
unambiguous — every count is a **pair** count, not an episode count.

On the real GDG `events` cluster the number is stark and stays visible:
**`ws_share_pct` = 100.0** (all 506 divergent pairs excused) with
**`ws_would_be_intra` = 164**. This is not a healthy signal — it is the
measurement telling us it cannot see (next section).

### `resolution` — degeneracy diagnostic (a weak measure is not a verdict)

When a cluster's divergent-pair cosines concentrate in a band narrower than
`degenerate_band_width` (0.05) across at least `degenerate_min_pairs` (10),
the line carries `resolution: "degenerate"` and the `band_width`. On the
GDG `events` cluster **all 506 divergent pairs sit at one cosine (band
width 0.0000)** — the divergence measure cannot separate a mild
contradiction from lexically diverse but consistent follow-ups, so *any*
threshold placed inside that bin is arbitrary. The flag is **diagnostic
only**: it is logged, never blocks, and `unstable` is still computed. Same
principle as PreEvidence ≠ Evidence — a weak measurement must not
masquerade as a strong verdict. Practical payoff: a finer embedder spreads
the band, and the gain becomes measurable. Pinned by
`test_degenerate_cluster_is_flagged_never_blocking` /
`test_spread_cluster_resolves`.

**Known limitation (moderate-band blindness on tool-bearing clusters).**
A MODERATE preference flip (directive cosine between 0.10 and 0.35)
co-occurring with a differing tool_result is still classified world_state
and excluded. Investigation confirmed the blindness directly: a synthetic
moderate flip (cosine 0.191, differing tool_result, 2 days apart) injected
into `events` classifies as `world_state`, absorbed. Only SEVERE
divergence (<0.10) surfaces (the adversarial guard). This is **not fixed by
a threshold**: on the degenerate `events` band, `world_state_min_cosine=0.20`
excuses everything (blind) and `=0.25` flags all 506 (a wholesale FALSE
positive, since `events` carries no labeled contradiction). Closing it
needs a finer embedder AND the fixture debt below.

### Fixture debt (recorded, deliberately not fixed here)

All four labeled `intra_cluster` contradictions in the GDG fixture live in
the tool-**less** `newsletter` cluster (`news-5/8/22/25`) — where they are
correctly flagged, since no tool means no world_state excuse. But
world_state masking can only occur on a tool-**bearing** cluster. **The
fixture therefore never exercises the case the classifier was built to
test.** Calibrating the moderate band requires BOTH a planted moderate
contradiction inside a tool-bearing cluster (differing tool_result,
directive cosine clearly separable from the lexical-noise floor) AND a
finer embedder that gives that separation a real spread. Until both exist,
the moderate-band verdict on tool-bearing clusters is `resolution:
degenerate`, by design.

### GDG demo — competition, not a clean room (`examples/gdg_demo.py`)

Replaying the `events` candidate against the raw fixture prints
`capture=1.000 / false=0.000` — a tautology from two biases: a **clean-room
build** (no incumbent to compete) and the **degenerate** `events` cluster
(45 identical openers, so no incumbent can own a *fraction* of it). The
demo corrects the first with a **legitimate** pre-seeded incumbent
(`venue_booking`, a real prior agent that reserves rooms and already owns
the reworded "book the room" phrasings): capture falls **1.000 → 0.600**,
honest topology competition. `test_gdg_demo.py` pins both.

The non-trivial **`false_trigger` = 0.143 is obtained by planting its
cause**: one adversarial "bridge" episode that reads as sponsor work (joins
that cluster) yet clears the candidate's bar. This is a deliberate
construct — exactly like `prompt_history_adversarial.jsonl` — not an
emergent false trigger. The GDG fixture's ten labeled *routing* threads do
NOT produce one on their own: their openers top out at cosine 0.522 to the
`events` centroid, below the 0.6 firing bar, so real routing traffic is
correctly never captured. The bridge exists only to show the false-trigger
machinery fires under competition.

## Realism run — re-measurement (frozen realistic fixtures)

All numbers below are on the realistic freeze-once fixtures (`examples/
phrasing.py` banks; generators reproducible on demand, never run in CI).
Grouped by the PLANTED intent (thread prefix in the committed `.jsonl` +
sidecar), never by detected cluster — the detector fragments, so "the cluster"
is not a thing the detector actually forms.

### Detector recovery (GDG ground-truth, 516 msgs / 246 episodes / 112 days)

| planted intent | occurrences | distinct openers | detected clusters |
|---|---|---|---|
| events | 10 | 10 | 9 |
| newsletter | 16 | 12 | 11 |
| speakers | 12 | 12 | 11 |
| sponsors | 14 | 12 | 10 |
| agenda_meetup | 9 | 8 | 6 |
| agenda_workshop | 9 | 8 | 4 |
| venue_policy | 8 | 8 | 8 |

63 detected clusters total; 22 reach the ≥3-occurrence signal gate but none
maps cleanly to a planted intent (they fragment AND merge on shared domain
tokens). Recovery is REPORTED, not gated (`test_gdg_routing_intents_fragment_
under_realistic_variety`, `test_holdout_discovery_structural_sanity`).

### Stability per planted intent (was: band 0.0000, ws_share 100%, all stable)

| intent | unstable | resolution | band_width | ws_share_pct | ws_would_be_intra |
|---|---|---|---|---|---|
| events (tool) | True | resolved | 0.3381 | ~30% | 2 |
| newsletter | True | resolved | 0.3474 | 0% | 0 |
| speakers (tool) | True | resolved | 0.2691 | 0% | 0 |
| sponsors (tool) | True | resolved | 0.3464 | 0% | 0 |
| agenda_meetup | True | resolved | 0.1760 | 0% | 0 |
| venue_policy | True | resolved | 0.3354 | 0% | 0 |

The band is no longer degenerate anywhere with divergent pairs — the
`band_width = 0.0000` of the old fixture was purely a templating artifact
(`test_events_intent_is_no_longer_degenerate`). NOTE the over-flag side of
this: with realistic follow-up variety the classifier reads lexical spread as
"divergence", so intents that should be clean (e.g. `venue_policy`'s temporal
evolution) are now flagged unstable and their candidate is suppressed
(`test_gdg_venue_policy_temporal_recovery_now_blocked`). The directive-cosine
divergence measure conflates paraphrase with contradiction — the same embedder
limitation, one layer down.

### Replay (events planted-centroid — the *ideal* trigger)

`capture = 0.500`, `false_trigger = 0.061`, `historical_cost = 2.44`. Even the
mean of all `events` openers matches only half of them at 0.6 — the old
`capture = 1.000` required identical openers. (The constructed competition demo
`gdg_demo.py` still shows `1.000 → 0.600` with a seeded incumbent + labeled
bridge; it is a deliberate illustration on a constructed window, not realistic
usage.)

### Holdout discovery (process-independent, 109 msgs / 41 episodes)

**0 agents discovered** (old templated holdout: 2 of 3). Each recurring
pattern (`meetup-prep`, `outreach`, `venue`, 9 occurrences each) fragments into
8–9 clusters, none reaching the 3-occurrence gate. Reported, not gated.

### world_state blindness — structural or artifact? (the revisited question)

Both, precisely delimited. On an injected MODERATE contradiction (directive
cosine 0.114) that co-occurs with a differing `tool_result`, the pair is STILL
classified `world_state` and absorbed — so the *rule-level* blind spot
(moderate divergence + differing tool_result → world_state, only severe < 0.10
rescued by adjustment 3) is **structural**, and realistic spread did not
dissolve it. But the *cluster-level* wholesale blindness ("world_state absorbs
100%, nothing can ever surface") **was an artifact** of degenerate data: on the
spread `events` intent world_state absorbs only ~30%, real `intra_cluster`
pairs surface through non-masked pairs, and the intent is now flagged unstable.
A genuine contradiction that does NOT happen to coincide with a world change is
now detected; one that does is still masked. No classifier change was made —
this is a report (the realism-run instruction).

### Scope note — the adversarial/rejection source is still templated

`examples/make_fixture.py` (→ `prompt_history.jsonl`,
`prompt_history_adversarial.jsonl`, the four hand-authored `*_agent.yaml`, and
the live `full_loop.sh` / dashboard demo) has NOT been de-templated in this
run. It is the live-demo backbone; de-templating it collapses the hand-authored
recap/standup/incident demo into the same fragmentation shown above, and the
embedder upgrade (next run) may restore clustering and let the demo be rebuilt
properly. It is called out here rather than silently left: the realism guard
covers the GDG and holdout sources; extending it to the adversarial source is
deferred with the demo rework.
