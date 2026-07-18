"""Episode segmentation — silence threshold + explicit markers (v1, no BOCPD).

Contract (replay-validation skill, BLUEPRINT §9 decision 1 as settled in the
approved P1 plan):
- Split on silence > 2x the user's median inter-message gap, floor 30 min;
  explicit markers ("thanks", new-thread) split unconditionally.
- Closure classification: `success` (explicit marker / no return) vs
  `abandoned` (no success marker AND no return to cluster). Abandoned
  episodes are EXCLUDED from cost baselines (anti-Goodhart guard, part 7).
- Cold start: <14 days of history or <20 episodes => no candidates; the
  detector observes silently and logs {"op":"detector_observing",...}.

Implemented in commit 6 (feat(detect): episodes).
"""
