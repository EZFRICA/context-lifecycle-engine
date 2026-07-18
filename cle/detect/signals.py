"""Reformulation vs recurrence classification.

Contract (replay-validation skill):
- Reformulation: >=3 in-window episodes at cost >1.5x the user's baseline.
- Recurrence: stable period over >=3 occurrences.
- Thresholds are config with article defaults, ALWAYS relative to the
  per-user baseline, never absolute.

Implemented in commit 7 (feat(detect): clusters + signals).
"""
