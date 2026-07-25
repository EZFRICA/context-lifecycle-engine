"""Minimal detector (v1) — the first cardinal pillar.

CLE need: candidate agents are detected from usage, never predicted
(BLUEPRINT §1). v1 detects via episode segmentation (`episodes`),
incremental intent clustering over an `Embedder` substrate (`clusters`,
`embedders`), and recurrence/reformulation counting against per-user
baselines (`signals`). `stability` classifies intra-cluster divergence and
can veto a birth. BOCPD segmentation is a v2 refinement, stubbed only.

Measured scope (docs/METRICS.md): on realistic phrasing this pipeline
recovers a MINORITY of the intents actually present, and the stability
classifier is unsound outside the vector space its heuristic was
calibrated for — where it reports `unavailable` rather than a verdict.
"""
