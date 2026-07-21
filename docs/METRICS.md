# CLE Metrics Inventory — Article 9 Skeleton

Every number `examples/full_loop.sh` produces, with its provenance, honest
scope, and the **test that pins it**. The suite has **187 tests (+1 opt-in integration) across 22 files**
(`uv run pytest`); each metric below names the test(s) that guard its
behaviour.

> **Numbers vs. substrate.** The replay numbers (`capture_rate`,
> `false_trigger_rate`, `historical_cost`, `closure_distribution`) are computed
> from the **embedder + trigger geometry** and are identical whether the build
> runs on a real Gemini model or a stub — only the `model_fingerprint` depends
> on the model. So these numbers are reproducible offline even though the
> system runs on real models locally.

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
  (`gemini-3.1-flash-lite` → `gemini-flash-latest`) moves 5/5 probes
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
   live Gemini model by default (`gemini-3.1-flash-lite`); the fingerprint runs
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
