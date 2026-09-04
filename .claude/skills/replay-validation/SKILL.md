---
name: replay-validation
description: Rules for the replay validation stage of cle build and for the minimal detector (episodes, clusters, embedders, signals, stability). Use when implementing or reviewing cle/detect or cle/build/replay.py.
---

# Replay Validation & Minimal Detector

## What replay proves — and what it cannot
Replay answers ONE question: would this candidate's trigger have fired on the
right past episodes? It can never rate answer quality — yesterday's user
cannot score an alternative answer. Outputs are `PreEvidence`, and the type
system keeps them out of promotion paths. Any comment, log, or docstring
implying replay measures quality is a review-blocking error.

## The replay run
Inputs: candidate Image (trigger included), prompt history window (default
30d), current topology (A, B, C routing), the candidate's `mounted_tools`.
Procedure:
1. **Provenance gate** — the candidate's `embedder_id` must match every
   incumbent's, else `SpaceMismatchError`. Cosines across vector spaces are
   category errors, not small numeric ones.
2. Re-segment the window into episodes (v1: silence threshold + explicit
   markers; BLUEPRINT §9 decision 1).
3. For every episode, evaluate routing against topology ∪ {candidate}. An
   episode whose `requires_tool` is not in `mounted_tools` is NOT captured —
   but it STAYS IN THE DENOMINATOR, so capture drops honestly instead of
   hiding the capability gap. `tool_result` is frozen decor: readable, never
   asserted correct (that would be answer quality).
4. Report:
   - `capture_rate` = captured in-cluster episodes / total in-cluster episodes
   - `false_trigger_rate` = captured OUT-of-cluster episodes / total
     out-of-cluster episodes  ← must replay out-of-cluster traffic; a capture
     rate without a false-trigger rate is meaningless and fails review.
   - `historical_cost` = mean iterations of in-cluster episodes under the
     current topology (the birth justification number).
Determinism: same window + same candidate ⇒ same report (property test).
Replay touches no live traffic, no store writes except the build log.

## Minimal detector (v1 — no BOCPD)
- Episodes: split on silence > threshold or explicit markers ("thanks",
  new-thread). Closure classification: `success` (explicit marker / no
  return), `reformulated` (no marker, returned to cluster in window),
  `abandoned` (no marker, no return, cost > 1.5× baseline) — abandoned
  episodes are EXCLUDED from cost baselines (the anti-Goodhart guard from
  part 7).
- Clusters: embed the episode opener behind the `Embedder` Protocol,
  incremental clustering; per cluster keep frequency, mean cost, trend,
  temporal distribution.
- **The similarity threshold is a property of the VECTOR SPACE, never a global
  constant.** It travels with `embedder_id` (`CLUSTER_THRESHOLD_BY_EMBEDDER`):
  0.6 for `stub:hashed64`, 0.775 for `google:gemini-embedding-2:768`.
  Bag-of-tokens puts same-domain text at ~0.2–0.4, a real sentence embedder at
  ~0.7–0.9 — one number cannot serve both. An unmapped embedder falls back to
  the config value and must be swept before it is trusted.
- Signals: reformulation = ≥3 in-window episodes at cost >1.5× user baseline;
  recurrence = stable period over ≥3 occurrences. Thresholds are config with
  article defaults; ALWAYS relative to the per-user baseline, never absolute.
- Per-user baseline: median iterations across the user's clusters, recomputed
  daily, excluding abandoned closures.

## Stability gating (`cle/detect/stability.py`)
Before synthesis, intra-cluster divergence is classified (intra_cluster /
grey_zone / temporal / world_state). Then:
- `unstable` → **veto**: no candidate ("don't automate a self-contradicting
  pattern");
- `unavailable` → **not a veto**: the candidate is born carrying
  `stability="unavailable"`, a gap disclosed at the human gate;
- never record `stable` when the check did not run.

## Measured reality — do not re-derive these the hard way
Recorded so no one repeats an assumption the measurements already refuted.
Fixture numbers and their provenance: docs/METRICS.md. Numbers measured on real
corpora, each with its pinning key and reproduction command: docs/FINDINGS.md.
- **Detection was only clean because the fixtures were templated.** On
  realistic phrasing the v1 embedder fragments every intent into
  near-singletons; holdout discovery falls to 0.
- **A real embedder is not a drop-in.** At the stub's threshold it
  over-merges (2 clusters, `false_trigger` 0.632). Recalibrated it beats v1
  but still recovers a minority of planted intents.
- **Cosine is the wrong operator for contradiction.** It measures topical
  relatedness: planted OPPOSING directives score 0.62–0.86 *because they are
  about the same thing*. The four-type taxonomy is therefore inert outside
  `stub:hashed64`, and no threshold rescues it — it needs a signed/entailment
  operator, which is not in v1 scope.
- **Candidate counts never stand bare.** Report them with purity against the
  planted intents (GENUINE / FRAGMENT / SPURIOUS); a bare count hides
  noise agglomerates.
- **The floor is OCCURRENCES PER INTENT, not episode density.** ~6 for a first
  cluster, ~10 for reliable recovery. Episode count predicts nothing: 200
  episodes across 200 distinct intents produce no cluster. R24 framed this as
  density and was wrong.
- **Recovery and false-trigger are one measurement seen from two ends.** On
  Stack Overflow moderator ground truth the detector groups 26/39 components
  (67%, against ~2% at random) at `false_trigger_rate` 0.580. Publishing either
  alone publishes half a measurement: grouping everything into one cluster
  scores 100% on the first and 1.0 on the second.
- **The signal is caudal.** Floor 0.464 on raw text, 0.519 to 0.561 on facets;
  factor 1.08 on the mean but 12.9 on the share above 0.7. Anything reading mean
  similarity sees ~0.55 everywhere and concludes nothing.

## Cold start
A user with <14 days of history or <20 episodes gets NO candidates — the
detector observes silently. Log `{"op":"detector_observing",...}` so the state
is visible in `cle log`.

## Fixtures — three sources, three roles
`ground truth` (recovery) · `adversarial` (rejection) · `holdout`
(discovery — imports NOTHING from `cle`, and is the only independent
confirmation point). Determinism comes from the **committed** `.jsonl`, not
from a deterministic generator. The realism guard asserts DATA properties
grouped by PLANTED intent (≥8 distinct openers, no sentence >15%, timing not
single-valued) — never by detected cluster, since recovery is measured, not
gated.
