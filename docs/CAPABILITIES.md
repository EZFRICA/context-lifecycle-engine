# CLE — System Capabilities

A résumé of everything the Context Lifecycle Engine does, why, and where each
capability is demonstrated. The system has two cardinal pillars — **detection**
(agents emerge from usage) and **lifecycle** (they earn or lose standing on
lived evidence) — over a content-addressed store, a runtime, and a live
dashboard. Everything below is exercised by `examples/full_loop.sh` and pinned
by the 212-test suite unless noted.

> **Realism-run caveat (read `docs/METRICS.md` HEADLINE FINDING first).** The
> detection capabilities below describe the mechanism, not its recovery rate on
> realistic data. When the templated fixtures were replaced with genuinely
> varied usage, the v1 bag-of-tokens embedder (cosine 0.6) fragmented every
> recurring intent into near-singletons and holdout discovery fell to **0**.
> v1 detection clustered cleanly only because the old fixtures were templated.
>
> **Embedder upgrade run (done).** A real model
> (`google:gemini-embedding-2:768`, frozen vectors, offline CI) is now available
> behind the Protocol. It is **not a drop-in**: at the unchanged 0.6 threshold it
> over-merges everything into 2 clusters and `false_trigger` jumps 0.061 → 0.632.
> Recalibrated to 0.775 it beats v1 (holdout discovers all 3 planted patterns vs
> 0), but GDG recovery still tops out at 2/7. And it **breaks the contradiction
> classifier entirely** — zero divergent pairs, because cosine measures topical
> relatedness, not contradiction. Threshold change is proposed, NOT applied.

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
- **Incremental intent clustering** — episode openers embedded by a dedicated
  `Embedder` (deterministic hashed-token embedder in v1, offline) and clustered
  by cosine ≥ 0.6; per-user baseline = median iterations, recomputed daily.
- **Two signals** — **recurrence** (stable period over ≥ 3 occurrences) and
  **reformulation** (≥ 3 episodes at cost > 1.5× baseline); thresholds are
  always relative to the user, never absolute.
- **Evidence-gated, not eager** — a weak cluster (`onboard_setup`, 2 occurrences)
  yields **no** candidate; a cold user (< 14 days / < 20 episodes) gets none and
  logs `detector_observing`.
- **Result**: the fixture detects three genuinely distinct agents — `weekly_recap`
  (recurrence), `standup_digest` (recurrence), `incident_triage` (reformulation)
  — each with its own centroid, probes, fingerprint, and cost. *Demo step 1–2.*

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
  (e.g. `weekly_recap` = 0.60 because `status_report` owns the reworded episodes).
- **`false_trigger_rate`** — out-of-cluster traffic the trigger would steal;
  always computed alongside capture. The adversarial window pairs one firing
  "bridge" with several near-miss traps that are correctly rejected, yielding
  ≈ 0.081 for the recap family — non-trivial, and lower than the bridge alone.
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

---

## Test coverage — 212 tests (+1 opt-in integration), 27 files (`uv run pytest`)

Every capability above is guarded by property and unit tests. No test needs a
real model, an API key, or the network (stub fingerprinters internally); CI runs
the suite plus an offline `full_loop.sh` smoke (`CLE_MODEL_A/B=stub-model-*`).

| Area | Files (tests) | What they pin |
|---|---|---|
| Hashing & store | `test_content_hash` (6), `test_backends` (6) | canonical JSON/sha256; Protocol conformance; mobile vs immutable refs |
| Two-hash / tag targets | `test_tag_targets` (5) | source ≠ image namespaces; tags reject non-image / non-JSON |
| Integrity | `test_integrity` (4), `test_resolver` (5) | corrupt read → log + refetch + raise; resolve fails fast, writes nothing |
| Evidence types | `test_evidence_types` (6) | PreEvidence/Persistence rejected by the promotion gate at type level |
| Detection — episodes | `test_episodes` (19) | silence threshold (both sides of 20-gap boundary); markers; closures; cold-start |
| Detection — clusters | `test_clustering` (6) | embedding determinism/normalization; disjoint vocab separates |
| Detection — signals | `test_signals` (10) | recurrence & reformulation; baselines relative to the user, excl. abandoned |
| Build | `test_build_invariants` (6), `test_staged_failure` (3) | two-hash, determinism, probe-hash coverage, one log line; staged failure writes nothing |
| Replay | `test_replay` (5), `test_adversarial_fixture` (1) | both rates always computed; **topology competition lowers capture**; determinism; non-trivial false-trigger |
| Holdout discovery | `test_holdout_discovery` (1) | structural sanity — ≥1 agent, cold-start gate, well-formed logs, real false-trigger ≤ ceiling; **reports** capture/false/cost but asserts no exact values |
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

See `docs/METRICS.md` for the per-number provenance and `docs/BLUEPRINT.md` for
the governing contract.

### GDG enriched run additions
Tool-aware triggering (declared/resolved, never executed; two-stage gating:
resolve fails fast on missing library tool or unmounted trigger
requirement; replay capture requires centroid AND mount), SqliteStore
(persistent, inspectable, default-suite eligible), and the
four-contradiction taxonomy with its guards (grey-zone total partition,
no-tool-never-world_state, severe-divergence adversarial override) — see
docs/METRICS.md for the table and stated limits.

**Resolution honesty (Option B extended).** The `cluster_stability` line
carries `world_state_attribution` (`ws_would_be_intra`, `ws_share_pct`) so
the exclusion's reach is permanently visible — on the real `events` cluster
it is 100%. It also carries a `resolution` flag: when the divergent cosines
concentrate too narrowly (the `events` band width is 0.0000, a single
value) the cluster is `degenerate` — **unresolvable at the current
measurement resolution**, neither stable nor unstable. Diagnostic only,
never blocking (a weak measure is not a verdict; PreEvidence ≠ Evidence).
The moderate-band blind spot on tool-bearing clusters and the fixture debt
(all planted contradictions live in the tool-less cluster) are recorded in
docs/METRICS.md. **`examples/gdg_demo.py`** shows topology competition: a
legitimate incumbent drops the `events` candidate's capture from 1.000 to
0.600, and a deliberately-planted, documented bridge episode yields a
non-trivial false_trigger (0.143) — no clean-room tautology.
