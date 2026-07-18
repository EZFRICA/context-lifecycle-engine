"""Minimal detector (v1) — the first cardinal pillar.

CLE need: candidate agents are detected from usage, never predicted
(BLUEPRINT §1). v1 detects via episode segmentation, incremental intent
clustering, and recurrence/reformulation counting against per-user
baselines. BOCPD segmentation is a v2 refinement, stubbed only.
"""
