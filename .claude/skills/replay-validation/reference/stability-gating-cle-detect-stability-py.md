## Stability gating (`cle/detect/stability.py`)
Before synthesis, intra-cluster divergence is classified (intra_cluster /
grey_zone / temporal / world_state). Then:
- `unstable` → **veto**: no candidate ("don't automate a self-contradicting
  pattern");
- `unavailable` → **not a veto**: the candidate is born carrying
  `stability="unavailable"`, a gap disclosed at the human gate;
- never record `stable` when the check did not run.
