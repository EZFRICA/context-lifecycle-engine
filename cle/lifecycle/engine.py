"""Lifecycle engine — shadow mode in v1.

Contract (BLUEPRINT §6): humans move tags via `cle tag`; the engine runs
the part-7 state-machine thresholds (config, article defaults) in shadow
and logs what it WOULD have done — actor engine:shadow, never a ref
write. The human/engine divergence log is a deliverable and the
calibration set for going live in v2.

Threshold defaults (decision, documented: the article gives the shape —
cost ratio against the historical baseline, minimum lived occurrences —
these constants instantiate it):
- promote trial->active: >=3 occurrences at cost_ratio <= 0.8
- demote active->trial: >=3 occurrences at cost_ratio >= 1.1
- archive trial->archived: >=5 occurrences at cost_ratio >= 1.3
  (an agent that makes things worse repeatedly is not retried forever)
"""

from pydantic import BaseModel

from cle.oplog import OpLog
from cle.store.commits import Evidence


class EngineThresholds(BaseModel, frozen=True):
    promote_min_occurrences: int = 3
    promote_max_cost_ratio: float = 0.8
    demote_min_occurrences: int = 3
    demote_min_cost_ratio: float = 1.1
    archive_min_occurrences: int = 5
    archive_min_cost_ratio: float = 1.3


def shadow_decide(
    *,
    state: str,
    evidence: Evidence,
    thresholds: EngineThresholds,
    image_hash: str,
    oplog: OpLog,
) -> str:
    """Evaluate the state machine on lived evidence; log the would-move.

    Returns the decision ("active" | "trial" | "archived" | "hold") and
    ONLY logs — a shadow engine that writes refs is a live engine, which
    is v2 behind the divergence calibration this log feeds.
    """
    would = "hold"
    if (
        state == "trial"
        and evidence.occurrences >= thresholds.promote_min_occurrences
        and evidence.cost_ratio <= thresholds.promote_max_cost_ratio
    ):
        would = "active"
    elif (
        state == "active"
        and evidence.occurrences >= thresholds.demote_min_occurrences
        and evidence.cost_ratio >= thresholds.demote_min_cost_ratio
    ):
        would = "trial"
    elif (
        state == "trial"
        and evidence.occurrences >= thresholds.archive_min_occurrences
        and evidence.cost_ratio >= thresholds.archive_min_cost_ratio
    ):
        would = "archived"

    oplog.emit(
        "tag",
        actor="engine:shadow",
        image=image_hash,
        from_state=state,
        evidence=evidence.model_dump(),
        would=would,
    )
    return would
