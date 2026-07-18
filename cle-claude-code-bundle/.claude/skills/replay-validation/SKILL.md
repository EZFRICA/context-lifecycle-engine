---
name: replay-validation
description: Rules for the replay validation stage of cle build and for the minimal detector (episodes, clusters, signals). Use when implementing or reviewing cle/detect or cle/build/replay.py.
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
30d), current topology (A, B, C routing).
Procedure:
1. Re-segment the window into episodes (v1: silence threshold + explicit
   markers; see open decision 1 in BLUEPRINT §9).
2. For every episode, evaluate routing against topology ∪ {candidate}.
3. Report:
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
  return), `abandoned` (no success marker AND no return to cluster) —
  abandoned episodes are EXCLUDED from cost baselines (the anti-Goodhart
  guard from part 7).
- Clusters: embed the episode opener (dedicated small embedder — see open
  decision 2), incremental clustering; per cluster keep frequency, mean cost,
  trend, temporal distribution.
- Signals: reformulation = ≥3 in-window episodes at cost >1.5× user baseline;
  recurrence = stable period over ≥3 occurrences. Thresholds are config with
  article defaults; ALWAYS relative to the per-user baseline, never absolute.
- Per-user baseline: median iterations across the user's clusters, recomputed
  daily, excluding abandoned closures.

## Cold start
A user with <14 days of history or <20 episodes gets NO candidates — the
detector observes silently. Log `{"op":"detector_observing",...}` so the state
is visible in `cle log`.
