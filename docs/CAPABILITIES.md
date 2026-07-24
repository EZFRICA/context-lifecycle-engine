# CLE — System Capabilities

A résumé of everything the Context Lifecycle Engine does, why, and where each
capability is demonstrated. The system has two cardinal pillars — **detection**
(agents emerge from usage) and **lifecycle** (they earn or lose standing on
lived evidence) — over a content-addressed store, a runtime, and a live
dashboard. Everything below is pinned by the 219-test suite unless noted.

> ## ⚠ Read this before any number below
>
> This document describes **mechanisms**. Two runs since have measured how well
> those mechanisms actually work, and the answers change what the numbers mean.
> Full detail and provenance in `docs/METRICS.md`; the short version:
>
> **1. v1 detection only clustered because the fixtures were templated.** Once
> the fixtures carried genuinely varied human phrasing, the v1 bag-of-tokens
> embedder shattered every recurring intent into near-singletons and holdout
> discovery fell to **0**.
>
> **2. A real embedding model helps detection, but is not a drop-in.** At the
> old 0.6 threshold it over-merges everything into 2 clusters and
> `false_trigger` jumps 0.061 → 0.632. Recalibrated to **0.775** (approved,
> scoped to `embedder_id`) it beats v1 — the holdout births a pure candidate for
> all 3 patterns (**2 clean recoveries + 1 pure fragment**, R10) — but GDG
> recovery still tops out at 2/7, and of its 6 born candidates only 2 are
> genuine (R10).
>
> **3. It breaks contradiction detection outright.** Cosine measures topical
> relatedness, not contradiction, so the four-type taxonomy (§9) detects
> nothing in a real embedding space. The classifier now reports `unavailable`
> there rather than a reassuring "stable".
>
> Numbers attributed to `weekly_recap` / `standup_digest` / `incident_triage`
> and to `examples/full_loop.sh` come from the **legacy templated demo source**
> (`make_fixture.py`), which has not been de-templated. They are labelled
> *legacy demo* throughout and should not be read as realistic-usage results.

---

## 1. Two-hash content-addressed store (`cle/store`)
- **`content_hash`** — the single hashing function (canonical JSON, sha256).
- **Two hashes, always** — a candidate's `SourceSpec.hash` is never its built
  `Image.hash`; the two live in disjoint namespaces via a `cle_kind` domain
  marker. *Invariant 1.*
- **Verify-on-read integrity** — every fetched component is re-hashed; a
  mismatch logs `integrity_violation`, refetches once, and raises rather than
  ever injecting corrupt bytes. *Demo step 8; §8 tamper test.*
- **Backends behind a Protocol** — `InMemoryStore` (default, the only test
  dependency), `FileStore` (persistent CLI/dashboard state), `WeaviateStore`
  (deferred). Refs: mobile `agents/<name>/<state>`, immutable
  `agents/<name>/v<semver>` (moving one raises), `topology/v<n>`.

## 2. Detection — the first pillar (`cle/detect`)
- **Episode segmentation** — splits a user's history on silence (> 2× their
  median inter-message gap, floor 30 min) and explicit markers (word-boundary
  matched). Closure classification (`success` / `reformulated` / `abandoned`);
  abandoned episodes are excluded from cost baselines (anti-Goodhart).
- **Incremental intent clustering** — episode openers embedded behind the
  `Embedder` Protocol and clustered by cosine; per-user baseline = median
  iterations, recomputed daily. The threshold is a property of the **vector
  space**, not a global default, and travels with `embedder_id`
  (`CLUSTER_THRESHOLD_BY_EMBEDDER`): **0.6** for `stub:hashed64`, **0.775** for
  `google:gemini-embedding-2:768`. One number cannot serve both — bag-of-tokens
  puts same-domain text at ~0.2–0.4, a real embedder at ~0.7–0.9.
- **Two signals** — **recurrence** (stable period over ≥ 3 occurrences) and
  **reformulation** (≥ 3 episodes at cost > 1.5× baseline); thresholds are
  always relative to the user, never absolute.
- **Evidence-gated, not eager** — a weak cluster (`onboard_setup`, 2 occurrences)
  yields **no** candidate; a cold user (< 14 days / < 20 episodes) gets none and
  logs `detector_observing`.
- **Result (*legacy demo*)**: on the templated `make_fixture.py` source the
  detector finds three distinct agents — `weekly_recap` (recurrence),
  `standup_digest` (recurrence), `incident_triage` (reformulation) — each with
  its own centroid, probes, fingerprint, and cost. *Demo step 1–2.* On the
  **realistic** fixtures this clean result does not reproduce: see the status
  block at the top and `docs/METRICS.md`.

## 3. Three-stage build (`cle/build`)
- **Resolve** — every `#ref` exists and re-hashes, or the build fails in
  milliseconds having written nothing. *Invariant 3 (staged builds consume
  nothing).*
- **Replay-validate** (see §4) — retrospective proof over the user's own past.
- **Assemble** — compile the prompt in declared order, freeze the probe set and
  the `model_fingerprint`, hash into an `Image`. Determinism: same source +
  components + substrate ⇒ same image hash. *Invariant 6 (proof expires).*
- **Substrate choice** — `cle build --model-id`: `current`/live (real Gemini,
  temperature 0), a named real model, or `stub-*` (deterministic offline).

## 4. Replay validation — trigger, never answer (`cle/build/replay.py`)
- **`capture_rate`** — fraction of the cluster's episodes the candidate's trigger
  would intercept **against the current topology** (BLUEPRINT §3.2). When an
  incumbent already owns part of the intent, capture is legitimately < 100%
  (*legacy demo*: `weekly_recap` = 0.60 because `status_report` owns the reworded
  episodes).
- **`false_trigger_rate`** — out-of-cluster traffic the trigger would steal;
  always computed alongside capture. The adversarial window pairs one firing
  "bridge" with several near-miss traps that are correctly rejected, yielding
  ≈ 0.081 for the recap family (*legacy demo*) — non-trivial, and lower than the
  bridge alone. On realistic data at the recalibrated threshold the `events`
  trigger measures 0.0044; at the *un*recalibrated 0.6 it measures 0.632.
- **`historical_cost`** — mean iterations of the in-cluster episodes (abandoned
  excluded) — the numeric justification of the birth.
- **Honesty** — outputs are `PreEvidence`, labelled *trigger only — not answer
  quality*; the period is carried but **not** replay-tested (`period_tested:
  false` — see `docs/METRICS.md` *Honest caveats §3* for the full note).
  Yesterday's user cannot score an alternative answer. *Invariant 5.*

## 5. Runtime — containers & the Goodhart boundary (`cle/runtime`)
- **Container** — a mutable record instantiating an image in a workspace; it
  exposes **no** read path to its own metrics. *Invariant 2, enforced by a
  reflection test that stays green through the runtime.*
- **Mounts** — ro/rw scopes; MCP handles as network mounts; rw store mounts must
  target mobile refs (content addresses and version refs can't absorb writes).
- **Metrics volume** — write-only `record(container_id, event)`; only the engine
  and the human read it (`read_events`), never the agent.
- **Divergent workspaces** — one image, two workspaces, genuinely different
  per-container metrics. *Demo step 3.*
- **Context-switch cost** — every workspace image switch logs `diff_blocks` +
  `diff_tokens` from a diff-only checkout — the founding metric of the series.
  *Demo step 4 (recap → incident: Δ 4 blk · 127 tok).*

## 6. Lifecycle — the second pillar (`cle/lifecycle`)
- **Seven-state ladder** — `archived → candidate → trial → ephemeral → pinned`
  (demotion/resurrection are transitions). *Demo steps 5–7.*
- **Three standards of proof, type-separated** — `PreEvidence` (replay),
  `Evidence` (trial, lived), `Persistence` (drift). A promotion API rejects the
  other two at type level; `require_evidence` is the single gate into the live
  states.
- **Shadow engine** — runs the part-7 thresholds and logs
  `actor:engine:shadow` with `would:` — it never writes a ref. *Demo step 6
  shows a real divergence (human `ephemeral` vs engine `would: hold`).*
- **Silence-demotion** — shadow rule, data-injected in v1: the runtime does not
  yet track last-solicitation; wiring it into `metrics_volume` is the v2 step.
  The rule fires correctly when the caller supplies the data; no v1 code path
  closes the loop automatically.
- **Topology writer** — the sole author of `topology.yaml`; every change is a
  store commit under `topology/v<n>` carrying its cause (evidence /
  pre_evidence / persistence / reason). `cle log topology.yaml` and `cle diff`
  render provenance and the learned delta.
- **Re-validation & proof expiry** — replays the frozen probe set against the
  served model; drift → `revalidation_failed` + auto-demote to trial. Live
  fingerprints run at temperature 0, so drift means the **model** changed, not
  the sampler. **Deliberate conservatism**: a *better* model also demotes, because
  the fingerprint is a change detector, not a quality detector; re-earning
  evidence under the new substrate is the designed cost. *Demo step 9.*
- **Drift-born succession** — after `weekly_recap` v1 drifts on model A, a v2 is
  rebuilt on model B with a **distinct** fingerprint and image — the successor
  is causally born from the drift. *Demo step 10.*

## 7. CLI (`cle …`)
`build · run · ps · tag · log · diff · revalidate · decline · clean`. Persistent
state under `--state-dir` (default `.cle/`). Every operation emits exactly one
JSON log line; upward tag moves carry `evidence`. *No log, no merge (invariant 4).*

## 8. Live dashboard (`dashboard/`)
FastAPI + SSE + a single Alpine page (no build step). Four zones — **Pulse**
(live oplog), **Births** (proposal cards with the human Approve/Decline gate),
**Lives** (7-state images, per-container metrics, switch-cost badges, the coral
drift card), **Topology** (state ladder, shadow strip, version diff). Click any
agent for a detail modal (identity, pre-evidence, resolved components, the
assembled prompt, the frozen probes). `▶ demo` walks the whole loop live on the
real model. Read-mostly: the only writes are Approve/Decline, through the CLI,
logged as `human:dashboard`. Metrics shown are the human's window — never fed
back to an agent.
- **Disclosed-gap marker on Births cards** — when a candidate's contradiction
  check could not run in its vector space (`stability="unavailable"`), the card
  shows a distinct dashed *"⚠ contradiction check did not run"* marker,
  deliberately **not** styled as an evidence badge (it is an absence, not a
  measurement). Derived at read time from `image.trigger.embedder_id` via the
  classifier's own predicate (`divergence_check_available`) — no new write path.
  The human decides at the override gate knowing the check did not run.

## 9. Embedder substrate & centroid provenance (`cle/detect/embedders.py`)
- **Three implementations behind one Protocol** — `RealEmbedder` (a ~20-line
  google-genai adapter, **generation-only**: it is the sole thing that needs a
  key and the network), `CachedEmbedder` (**the suite default** — pure dict
  lookup over committed vectors; a miss raises `CacheMissError` and never
  recomputes silently), and `StubEmbedder` (the deterministic v1 bag-of-tokens
  embedder, for synthetic-text unit tests).
- **Frozen vectors** — 247 distinct fixture texts embedded once
  (`google:gemini-embedding-2:768`) and committed, so CI is offline and
  deterministic. Two consumers embed two *shapes* of text: clustering/replay
  embed an opener, the stability classifier embeds the follow-ups **joined**.
- **Cache key = `sha256(embedder_id \0 text)`** — the same text in a different
  space is a different key, so a model change misses every key instead of
  silently reusing stale vectors. Integrity is a test: counts must match and no
  two distinct texts may share a vector (a batching collapse must fail the suite).
- **Centroid provenance** — `TriggerSpec` records `embedder_id`, and `Image.hash`
  covers the trigger, so **two images built on different embedders have
  different hashes**. A centroid is only meaningful inside the space that
  produced it: an embedder swap invalidates centroids exactly as a model swap
  invalidates a `model_fingerprint`, one layer deeper — and this one touches
  agent **identity**. Cross-space comparison raises `SpaceMismatchError`,
  enforced where routing actually compares (candidate vs each incumbent).
- **No `model_version`** — the embedding API exposes no version signal distinct
  from the model id; storing a placeholder would give false assurance about
  detecting silent provider-side drift.

## 10. Tool-aware triggering & contradiction classification
- **Tools are declarations, never executions** — two-stage gating: resolve fails
  fast on a missing library tool or an unmounted trigger requirement; replay
  capture requires centroid match **AND** tool mount, with unmounted-tool
  episodes staying in the denominator so the capability gap is visible.
  `tool_result` is frozen decor: read to classify divergence, never asserted
  correct (invariant 5).
- **`SqliteStore`** — persistent and inspectable, behind the same store Protocol
  as `InMemoryStore`/`FileStore`; conformance is parametrized across all three.

> **⚠ The four-contradiction taxonomy is INERT in a real embedding space.**
> It detects nothing there — zero divergent pairs across all seven planted
> intents. Cosine measures **topical relatedness, not contradiction**: the
> planted *opposing* directives score 0.62–0.86 because they *are* about the
> same thing. v1 only appeared to detect contradictions through lexical accident
> (opposing wording shares few tokens). **No threshold rescues this** — the bar
> would need to exceed 0.86, flagging every pair; it needs a signed/entailment
> operator, which is its own run. The `world_state` question is **superseded,
> not answered**: the rule is unreachable because nothing registers as divergent.
> The taxonomy is therefore valid **only for `embedder_id=stub:hashed64`**, and
> even there it is a lexical proxy rather than true contradiction detection.

- **Three-valued verdict** — `analyze_cluster_stability` returns `stable`,
  `unstable`, or **`unavailable`**; the last is returned in any space where
  directive-divergence-by-cosine is unsound, and the signal gate treats it as
  *not measured*: detection PROCEEDS and the candidate is born carrying
  `stability="unavailable"` in its provenance, surfaced at the human override
  gate. The check is a safety **veto** (an `unstable` cluster yields no
  candidate), never a precondition — blocking on its absence would stop the
  first pillar producing anything at all. **A non-measurement must never
  masquerade as a verdict**, but it is a disclosed gap, not a silent pass.
- **Permanent attribution + resolution diagnostic** — the `cluster_stability`
  line always carries `world_state_attribution` (`ws_would_be_intra`,
  `ws_share_pct`) so the exclusion's reach stays visible, and a `resolution`
  flag marking a cluster `degenerate` when its divergent cosines are too
  concentrated to resolve a verdict. Diagnostic only, never blocking.

## 11. Fixtures — freeze-once, with an anti-templating guard
- **Three sources, three roles** — ground-truth (recovery), adversarial
  (rejection), holdout (**discovery**, process-independent: it never imports
  `cle`). Determinism comes from the **committed `.jsonl`**, not from a
  templated generator; the generators are reproducible on demand and never run
  in CI.
- **Realism guard** (`test_fixture_realism.py`) — asserts DATA properties
  grouped by the **planted intent** (from the sidecar), never by detected
  clusters: ≥ 8 distinct openers per recurring intent, no sentence > 15% of
  messages, timing not single-valued. A fixture that regresses to templated text
  fails the suite instead of being discovered three runs later.
- **`examples/gdg_demo.py`** — topology competition rather than a clean-room
  tautology: a legitimate incumbent drops the candidate's capture 1.000 → 0.600,
  and a deliberately-planted, documented bridge episode yields a non-trivial
  `false_trigger` (0.143). The bridge is labelled a construct, not an emergent
  result.
- **Known debt** — the adversarial/demo source (`make_fixture.py`, the four
  hand-authored agent YAMLs, `full_loop.sh`, the dashboard demo) is **still
  templated** and is excluded from the realism guard.

---

## Test coverage — 219 tests across 26 files (+1 opt-in integration)

Every capability above is guarded by property and unit tests. **No test needs a
real model, an API key, or the network**: fingerprinters are stubbed and the
embedder is `CachedEmbedder` over committed vectors (a miss is an error, never a
silent recompute — and a test asserts no test module imports `RealEmbedder`).
CI runs the suite plus an offline `full_loop.sh` smoke (`CLE_MODEL_A/B=stub-*`).

| Area | Files (tests) | What they pin |
|---|---|---|
| Hashing & store | `test_content_hash` (6), `test_backends` (6), `test_sqlite_store` (32) | canonical JSON/sha256; Protocol conformance across 3 backends; mobile vs immutable refs |
| Two-hash / tag targets | `test_tag_targets` (5) | source ≠ image namespaces; tags reject non-image / non-JSON |
| Integrity | `test_integrity` (4), `test_resolver` (5) | corrupt read → log + refetch + raise; resolve fails fast, writes nothing |
| Evidence types | `test_evidence_types` (6) | PreEvidence/Persistence rejected by the promotion gate at type level |
| Detection — episodes | `test_episodes` (19) | silence threshold (both sides of the boundary); markers; closures; cold-start |
| Detection — clusters | `test_clustering` (6) | embedding determinism/normalization; disjoint vocab separates |
| Detection — signals | `test_signals` (10) | recurrence & reformulation; baselines relative to the user, excl. abandoned |
| **Embedder & provenance** | `test_embedder_provenance` (10) | suite default is `CachedEmbedder`; miss raises; no test imports `RealEmbedder`; embedder swap changes `Image.hash`; cross-space compare raises; **cache-collapse integrity** |
| Build | `test_build_invariants` (6), `test_staged_failure` (3) | two-hash, determinism, probe-hash coverage, one log line; staged failure writes nothing |
| Replay & tools | `test_replay` (5), `test_replay_capability` (5), `test_tools_gating` (18) | both rates always computed; competition lowers capture; capture = centroid **AND** mount; tools declared, never executed |
| **Contradiction taxonomy** | `test_contradictions` (23), `test_stability_classifier` (4) | the four types + guards; `unavailable` still births a candidate but with a disclosed gap, and never records stability=stable; `unstable` stays a hard veto |
| **Fixture realism** | `test_fixture_realism` (14), `test_gdg_fixture` (11) | ≥ 8 distinct openers per *planted* intent; no sentence > 15%; timing not single-valued; labels stay in the sidecar |
| Adversarial & demo | `test_adversarial_fixture` (1), `test_gdg_demo` (2) | a bridge yields non-trivial false-trigger; incumbent competition drops capture below 1.0 |
| Holdout discovery | `test_holdout_discovery` (1) | structural sanity only — cold-start gate, valid centroids, well-formed logs, false-trigger ≤ ceiling. The discovery **count is reported, not gated** |
| Runtime & Goodhart | `test_goodhart_boundary` (5), `test_runtime` (6) | Container has no metrics read path; FileStore/mounts; switch cost carries both diffs; solicit writes no store objects |
| Lifecycle | `test_lifecycle` (6) | proof ladder & gate; shadow decides but never writes; silence demotion; topology chain/diff; **revalidate holds then drifts** |

Key invariant tests by name: `test_two_hash_inequality`, `test_build_determinism`,
`test_image_hash_covers_probe_output_hashes`, `test_staged_failure_writes_nothing`,
`test_pre_evidence_not_evidence`, `test_container_*` (Goodhart reflection),
`test_existing_topology_wins_ties_and_reduces_capture`,
`test_revalidate_holds_then_drifts`. The real-substrate behaviour (proof holds on
the same Gemini model, expires on a different one) is validated live end-to-end
via the CLI, on top of the stub-based `test_revalidate_holds_then_drifts`.

---

## What the numbers do NOT prove (honesty)
- Replay tests the **trigger only**, never answer quality. The **period** is
  carried but not tested (`period_tested: false`); see `docs/METRICS.md`
  *Honest caveats §3* for the full note.
- A fingerprint delta proves the **substrate changed** — not that the agent is
  broken. A better model demotes just as a degraded one would (deliberate
  conservatism; `docs/METRICS.md` revalidation entry).
- **Silence-demotion** is a shadow rule, data-injected in v1 — the runtime does
  not yet track last-solicitation; wiring it into `metrics_volume` is the v2
  step. No reader should finish this document believing the silence loop is closed.
- Demo closures are **synthetic** CLI sugar; real closures come from the detector.
- A shared `model_fingerprint` between two agents means they probe the **same
  cluster on the same model** (substrate identity), not that they are the same
  agent — the three *detected* agents have distinct fingerprints.
- `capture_rate` is relative to the **current topology**, not an absolute.
- **Detection does not recover realistic usage.** At best 2/7 planted intents on
  the GDG fixture (v1: 0/7 at *its* best across a full sweep). The clean
  three-agent result is the legacy templated source only.
- **Contradiction classification is inert in a real embedding space** — cosine
  measures topical relatedness, not contradiction. Where it reports
  `unavailable`, nothing was measured; that is not a clean bill of health.
- **The 0.775 threshold rests on ONE independent confirmation** (the holdout: a
  pure candidate for all 3 patterns, 2 clean + 1 fragment — R10). The GDG sweep
  peak is *in-sample* — chosen on the data it is then scored against — and is not
  evidence. A second independent source should move it.
- **The adversarial/demo source is still templated**, so every *legacy demo*
  number above inherits that bias.

See `docs/METRICS.md` for the per-number provenance and `docs/BLUEPRINT.md` for
the governing contract.

