"""Lifecycle tags — mobile states and immutable versions.

Contract (cle-core-contracts, invariants 1 and 4-5):
- Tags attach to Image hashes only; tagging a source hash raises
  `TagTargetError` (guard lives in store/commits.py, used here).
- Upward tag moves REQUIRE `Evidence` (lived, from trial) — `PreEvidence`
  is rejected at type level. Every tag op logs one JSON line.

P3 implements the tag engine; P1 ships the evidence gate (commit 4) so no
promotion path can ever be written against replay output.
"""
