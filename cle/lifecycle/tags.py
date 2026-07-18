"""Lifecycle tags — mobile states and immutable versions.

Contract (cle-core-contracts, invariants 1 and 4-5):
- Tags attach to Image hashes only; tagging a source hash raises
  `TagTargetError` (guard lives in store/commits.py, used here).
- Upward tag moves REQUIRE `Evidence` (lived, from trial) — `PreEvidence`
  is rejected at type level. Every tag op logs one JSON line.

P3 implements the tag engine; P1 ships the evidence gate so no promotion
path can ever be written against replay output.
"""

from cle.store.commits import Evidence


def require_evidence(evidence: Evidence) -> Evidence:
    """The runtime teeth behind the type annotation on upward tag moves.

    Static typing already forbids passing PreEvidence or Persistence here;
    this check makes the boundary hold for dynamically built callers (the
    CLI, the shadow engine reading config) too. Exact-type on purpose: a
    subclass smuggling replay numbers under an Evidence face is the exact
    conflation invariant 5 forbids.
    """
    if type(evidence) is not Evidence:
        raise TypeError(
            f"upward tag moves require lived Evidence, got {type(evidence).__name__}"
        )
    return evidence
