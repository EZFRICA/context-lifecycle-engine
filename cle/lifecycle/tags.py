"""Lifecycle tags — mobile states and immutable versions.

Contract (cle-core-contracts, invariants 1, 4, 5):
- Tags attach to Image hashes only (assert_tag_target guards every path).
- Upward moves REQUIRE proof; require_evidence stays the ONLY promotion
  gate. Decision (documented, P3): pre-trial moves (birth->candidate,
  candidate->trial, archived->trial resurrection) carry PreEvidence —
  the only proof that can exist before an agent has lived; every move
  into `active` carries lived Evidence, no exception. Downward moves
  need no proof, only a logged reason.
- Every tag op logs one JSON line; version refs are write-once
  (backend-enforced ImmutableRefError).
"""

import time

from cle.oplog import OpLog
from cle.store.backends import StoreBackend
from cle.store.commits import Evidence, PreEvidence, assert_tag_target

# Part-7 ladder. archived sits below candidate: resurrection re-earns
# trial, never re-enters active directly.
STATE_RANK = {"archived": 0, "candidate": 1, "trial": 2, "active": 3}


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


class TagMoveError(Exception):
    """A state move that the ladder or its proof requirements reject."""


def move_state_tag(
    *,
    backend: StoreBackend,
    agent: str,
    image_hash: str,
    from_state: str | None,
    to_state: str,
    evidence: Evidence | None = None,
    pre_evidence: PreEvidence | None = None,
    reason: str | None = None,
    oplog: OpLog,
    actor: str,
) -> None:
    """Move an agent's mobile state tag, enforcing the proof ladder."""
    started = time.monotonic()
    if to_state not in STATE_RANK:
        raise TagMoveError(f"unknown state {to_state!r}; ladder is {sorted(STATE_RANK)}")
    assert_tag_target(backend, image_hash, oplog)

    upward = from_state is None or STATE_RANK[to_state] > STATE_RANK.get(from_state, 0)
    if to_state == "active":
        # THE promotion gate — lived evidence only, whatever the path.
        if evidence is None:
            raise TagMoveError("promotion to active requires Evidence")
        require_evidence(evidence)
    elif upward:
        if pre_evidence is None and evidence is None:
            raise TagMoveError(f"upward move to {to_state} requires pre_evidence (or evidence)")
    elif reason is None:
        raise TagMoveError("downward moves must state a reason (it is logged)")

    backend.move_ref(f"agents/{agent}/{to_state}", image_hash)
    oplog.emit(
        "tag",
        actor=actor,
        image=image_hash,
        from_state=from_state,
        to_state=to_state,
        evidence=evidence.model_dump() if evidence else None,
        pre_evidence=pre_evidence.model_dump() if pre_evidence else None,
        latency_ms=round((time.monotonic() - started) * 1000, 3),
        **({"reason": reason} if reason else {}),
    )


def tag_version(
    *, backend: StoreBackend, agent: str, semver: str, image_hash: str, oplog: OpLog, actor: str
) -> None:
    """Pin an immutable version ref (moving it later raises in the
    backend). Semver rule: major = trigger changed, minor = component ref
    swapped, patch = lifecycle thresholds only."""
    assert_tag_target(backend, image_hash, oplog)
    backend.move_ref(f"agents/{agent}/v{semver}", image_hash)
    oplog.emit("tag", actor=actor, image=image_hash, to_state=f"v{semver}")
