# CLE, System Capabilities

What the Context Lifecycle Engine does, why, and where each capability is
demonstrated. Two cardinal pillars, **detection** (agents emerge from usage)
and **lifecycle** (they earn or lose standing on lived evidence), over a
content-addressed store, a runtime, and a live dashboard. Pinned by the
**394-test** suite unless noted.

> ## ⚠ Read this before any number below
>
> This document describes **mechanisms**. How well they work on realistic data
> was measured separately (`docs/METRICS.md`), and the answers change what the
> numbers mean:
>
> **1. v1 detection only clustered because the fixtures were templated.** Given
> genuinely varied phrasing, the v1 bag-of-tokens embedder shattered every
> recurring intent into near-singletons; holdout discovery fell to **0**.
>
> **2. A real embedding model helps, but is not a drop-in.** At the old 0.6
> threshold it over-merges into 2 clusters and `false_trigger` jumps
> 0.061 → 0.632 (events intent, ideal centroid). Recalibrated to **0.775**
> (scoped to `embedder_id`) it beats v1, but GDG recovery tops out at **2/7**,
> and of the 6 candidates it births only **2 are genuine** (2 fragments,
> 2 spurious).
>
> **3. It breaks contradiction detection.** Cosine measures topical
> relatedness, not contradiction, so the four-type taxonomy (§10) detects
> nothing in a semantic space. The classifier reports `unavailable` there -
> a disclosed gap, never a reassuring "stable".
>
> Numbers attributed to `weekly_recap` / `standup_digest` / `incident_triage`
> and to `examples/full_loop.sh` come from the **legacy templated demo source**
> (`make_fixture.py`), labelled *legacy demo* throughout.

---

## 1. Two-hash content-addressed store (`cle/store`)
- **`content_hash`**: the single hashing function (canonical JSON, sha256).
- **Two hashes, always**: a candidate's `SourceSpec.hash` is never its built
  `Image.hash`; disjoint namespaces via a `cle_kind` domain marker. *Invariant 1.*
- **Verify-on-read integrity**: every fetched component is re-hashed; a
  mismatch logs `integrity_violation`, refetches once, and raises rather than
  ever injecting corrupt bytes. *Demo step 8.*
  

## 2. Detection, the first pillar (`cle/detect`)
- **Episode segmentation**: splits history on silence (> 2× the user's median
  inter-message gap, floor 30 min) and explicit markers. Closure classification
  (`success` / `reformulated` / `abandoned`); abandoned episodes are excluded
  from cost baselines (anti-Goodhart).
- **Incremental intent clustering**: openers embedded behind the `Embedder`
  Protocol, clustered by cosine. The threshold is a property of the **vector
  space**, not a global default, and travels with `embedder_id`: **0.6** for
  `stub:hashed64`, **0.775** for `google:gemini-embedding-2:768`. One number
  cannot serve both (bag-of-tokens puts same-domain text at ~0.2–0.4, a real
  embedder at ~0.7–0.9).
- **Two signals**: **recurrence** (stable period over ≥3 occurrences) and
  **reformulation** (≥3 episodes at cost > 1.5× baseline), always relative to
  the per-user baseline, never absolute.
- **Evidence-gated, not eager**: a weak cluster yields no candidate; a cold
  user (< 14 days / < 20 episodes) gets none and logs `detector_observing`.
- **Result (*legacy demo*)**: on the templated source the detector finds three
  distinct agents (`weekly_recap`, `standup_digest`, `incident_triage`), each
  with its own centroid, probes, fingerprint and cost. **On realistic fixtures
  this clean result does not reproduce**: see the status block.

## 3. Three-stage build (`cle/build`)
- **Resolve**: every `#ref` exists and re-hashes, or the build fails in
  milliseconds having written nothing. *Invariant 3.*
- **Replay-validate** (§4), retrospective proof over the user's own past.
- **Assemble**: compile the prompt in declared order, freeze the probe set and
  `model_fingerprint`, hash into an `Image`. Same source + components +
  substrate ⇒ same image hash. *Invariant 6.*
- **Substrate choice**: `cle build --model-id`: live Gemini (temperature 0), a
  named real model, or `stub-*` (deterministic offline).

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

## 5. Runtime, containers & the Goodhart boundary (`cle/runtime`)
- **Container**: a mutable record instantiating an image in a workspace, with
  **no** read path to its own metrics. *Invariant 2, enforced by reflection tests.*
- **Mounts**: ro/rw scopes; MCP handles as network mounts; rw store mounts must
  target mobile refs.
- **Metrics volume**: write-only `record()`; only the engine and the human read
  it, never the agent.
- **Context-switch cost**: every workspace image switch logs `diff_blocks` +
  `diff_tokens` (*legacy demo*: Δ 4 blk · 127 tok).

## 6. Lifecycle, the second pillar (`cle/lifecycle`)
- **Five-state ladder**: `archived(0) → candidate(1) → trial(2) →
  ephemeral(3) → pinned(4)`. Transitions are not an enumerated set: `move_tag`
  accepts any pair inside `STATE_RANK`, gated by rank + proof, a move into
  `ephemeral`/`pinned` demands lived `Evidence`, any other upward move demands
  `pre_evidence`, and every downward move demands a logged reason. Resurrection
  (`archived → trial`) works because `archived` ranks 0. Immutable
  `v<semver>` refs are a separate write-once namespace, not a state.
- **KNOWN DIVERGENCE from the published theory**: part 7 defines **seven**
  states; the code implements **five**. `pattern` and `deprecated` have **zero
  code representation**: no `STATE_RANK` entry, no literal anywhere in `cle/`,
  no tag ref, and no dashboard chip. (`deprecated` still has an orphan CSS rule
  in the dashboard stylesheet, dead style, never applied.) The engine's shadow
  verdicts are `hold`, `trial`, `ephemeral`, `pinned`, `archived`,
  `demote_silence`: again no `pattern`, no `deprecated`. This is a v1 gap
  recorded as such, not a renaming of the theory.
- **Three standards of proof, type-separated**: `PreEvidence` (replay),
  `Evidence` (trial, lived), `Persistence` (drift). The promotion API rejects
  the other two at type level.
- **Shadow engine**: runs the part-7 thresholds and logs `actor:engine:shadow`
  with `would:`; it never writes a ref. The human/engine divergence log is the
  calibration set for going live.
- **Silence-demotion**: a shadow rule, **data-injected** in v1; the runtime
  does not yet track last-solicitation. The loop is not closed.
- **Topology writer**: the sole author of `topology.yaml`; every change is a
  store commit under `topology/v<n>` carrying its cause.
- **Re-validation & proof expiry**: replays the frozen probe set against the
  served model; drift → `revalidation_failed` + auto-demote. **Deliberate
  conservatism**: a *better* model demotes too, because the fingerprint is a
  change detector, not a quality detector.
- **Drift-born succession**: a v2 rebuilt on the drifted substrate is a
  distinct image with a distinct fingerprint, causally born from the drift.

## 7. CLI (`cle …`)
`build · run · ps · tag · log · diff · revalidate · decline · dashboard · clean`.
Persistent state under `--state-dir` (default `.cle/`). Every operation emits
exactly one JSON log line; upward tag moves carry `evidence`. *Invariant 4.*

## 8. Live dashboard (`dashboard/`)
FastAPI + SSE + a single Alpine page (no build step). Four zones, **Pulse**
(live oplog), **Births** (proposal cards with the human Approve/Decline gate),
**Lives** (5-state images, per-container metrics, switch-cost badges, drift
card), **Topology** (state ladder, shadow strip, version diff). Read-mostly:
the only writes are Approve/Decline, routed through the CLI and logged as
`human:dashboard`. Metrics shown are the human's window, never fed back to an
agent.
- **Disclosed-gap marker on Births cards**: when a candidate's contradiction
  check could not run in its vector space, the card shows a dashed *"⚠
  contradiction check did not run"* marker, deliberately **not** styled as an
  evidence badge (it is an absence, not a measurement). Derived at read time
  from `image.trigger.embedder_id` via the classifier's own predicate, no new
  write path, so card and signal gate cannot disagree.

## 9. Embedder substrate & centroid provenance (`cle/detect/embedders.py`)
- **Three implementations behind one Protocol**: `RealEmbedder` (a ~20-line
  google-genai adapter, **generation-only**: the sole thing needing a key and
  the network), `CachedEmbedder` (**the suite default**: dict lookup over
  committed vectors; a miss raises `CacheMissError` and never recomputes), and
  `StubEmbedder` (the deterministic v1 bag-of-tokens embedder).
- **Frozen vectors**: 247 distinct fixture texts embedded once and committed,
  so CI is offline and deterministic. Two consumers embed two *shapes* of text:
  clustering/replay embed an opener, the stability classifier embeds the
  follow-ups **joined**.
- **Cache key = `sha256(embedder_id \0 text)`**: a model change misses every
  key instead of silently reusing stale vectors. Integrity is a test: counts
  must match and no two distinct texts may share a vector.
- **Centroid provenance**: `TriggerSpec` records `embedder_id`, and
  `Image.hash` covers the trigger, so **two images built on different embedders
  have different hashes**. An embedder swap invalidates centroids exactly as a
  model swap invalidates a fingerprint, one layer deeper, and this one touches
  agent **identity**. Cross-space comparison raises `SpaceMismatchError`,
  enforced where routing actually compares.
- **No `model_version`**: the embedding API exposes no version signal distinct
  from the model id; a placeholder would give false drift-detection assurance.

## 10. Tool-aware triggering & contradiction classification
- **Tools are declarations, never executions**: two-stage gating: resolve
  fails fast on a missing library tool or an unmounted trigger requirement;
  replay capture requires centroid match **AND** tool mount, with
  unmounted-tool episodes staying in the denominator so the capability gap is
  visible. `tool_result` is frozen decor: read to classify divergence, never
  asserted correct (*invariant 5*).

> **⚠ The four-contradiction taxonomy is INERT in a real embedding space.**
> Zero divergent pairs across all seven planted intents. Cosine measures
> **topical relatedness, not contradiction**: the planted *opposing* directives
> score 0.62–0.86 because they *are* about the same thing. v1 only appeared to
> detect contradictions through lexical accident. **No threshold rescues this**
>, the bar would need to exceed 0.86, flagging every pair; it needs a
> signed/entailment operator, which is its own run. The `world_state` question
> is **superseded, not answered**: the rule is unreachable because nothing
> registers as divergent. The taxonomy is valid **only for `stub:hashed64`**,
> and even there it is a lexical proxy.

- **Three-valued verdict**: `stable` / `unstable` / **`unavailable`**. An
  `unstable` cluster is **vetoed** (no candidate). `unavailable` is **not** a
  veto: the candidate is born carrying `stability="unavailable"`, surfaced at
  the human gate. Blocking on a check's absence would stop the first pillar
  producing anything at all. **A non-measurement must never masquerade as a
  verdict**: but it is a disclosed gap, not a silent pass.
- **Permanent attribution + resolution diagnostic**: the `cluster_stability`
  line always carries `world_state_attribution` (`ws_would_be_intra`,
  `ws_share_pct`) and a `resolution` flag marking a cluster `degenerate` when
  its divergent cosines are too concentrated to resolve a verdict. Diagnostic
  only, never blocking.

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

## Test coverage

The count, the per area table, and the classification of what a green suite
actually validates are in `docs/TESTING.md`.

The one line worth repeating here: **the suite is offline**, and a green run
pins the contract, not the production vector space. 161 of the assertions are
embedder agnostic and hold in any era; 31 pin the v1 stub mechanism only and do
not describe the production system.

---

## What the numbers do NOT prove

- Replay tests the **trigger only**, never answer quality; the period is
  carried but not tested.
- A fingerprint delta proves the **substrate changed**, not that the agent is
  broken.
- **Silence-demotion** is data-injected in v1, the loop is not closed.
- Demo closures are **synthetic** CLI sugar.
- `capture_rate` is relative to the **current topology**, not an absolute.
- The holdout tests' `Signal.stability` output is **not a verdict**: they call
  the ungated `detect_signal`, which never runs the contradiction check, so the
  field shows its default rather than a measured `stable`. Do not read it
  against the `unavailable` verdict documented elsewhere, they are different
  code paths, not a contradiction.
- **Detection does not recover realistic usage.** At best 2/7 planted intents
  on the GDG fixture (v1: 0/7 at *its* best across a full sweep). The clean
  three-agent result is the legacy templated source only.
- **Contradiction classification is inert in a real embedding space.** Where it
  reports `unavailable`, nothing was measured, that is not a clean bill of health.
- **The 0.775 threshold rests on ONE independent confirmation** (the holdout).
  The GDG sweep peak is *in-sample* and is not evidence.
- **The adversarial/demo source is still templated**, so every *legacy demo*
  number inherits that bias.

See `docs/METRICS.md` for per-number provenance and `docs/BLUEPRINT.md` for the
governing contract.
