"""Incremental intent clustering with per-user baselines.

Contract (replay-validation skill, BLUEPRINT §9 decision 2 as adopted in
the approved P1 plan):
- Embed the episode opener with a dedicated small embedder behind an
  `Embedder` Protocol (centroids must survive agent-model swaps; P1 ships a
  deterministic local embedder so tests need no network).
- Incremental clustering; per cluster keep frequency, mean cost, trend,
  temporal distribution.
- Per-user baseline: median iterations across the user's clusters,
  recomputed daily, excluding abandoned closures.

Implemented in commit 7 (feat(detect): clusters + signals).
"""
