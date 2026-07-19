"""Lifecycle engine — shadow mode in v1.

Contract (BLUEPRINT §6): humans move tags via `cle tag`; the engine runs
the part-7 state-machine thresholds (config, article defaults) in shadow
and logs what it WOULD have done — actor engine:shadow, never a ref
write. The human/engine divergence log is a deliverable and the
calibration set for going live in v2.

Threshold defaults (article values):
- promote trial->ephemeral: >=3 occurrences at cost_ratio <= 0.7
- pin ephemeral->pinned: >=10 occurrences (solicitations proxy) at
  cost_ratio <= 1.0 (stable-or-improving)
- demote ephemeral->trial: >=3 occurrences at cost_ratio >= 1.1
- demote pinned->ephemeral: >=3 occurrences at cost_ratio >= 1.1
- archive trial->archived: >=5 occurrences at cost_ratio >= 1.3
  (an agent that makes things worse repeatedly is not retried forever)
- silence demotion: > silence_factor × the pattern's period without
  solicitation (default 2.0×). Requires runtime-supplied
  days_since_last_solicitation; in v1 the shadow logs `would:
  demote_silence` when it can evaluate the rule.
"""

from pydantic import BaseModel

from cle.oplog import OpLog
from cle.store.commits import Evidence


class EngineThresholds(BaseModel, frozen=True):
    promote_min_occurrences: int = 3
    promote_max_cost_ratio: float = 0.7
    pin_min_solicitations: int = 10
    pin_max_cost_ratio: float = 1.0
    demote_min_occurrences: int = 3
    demote_min_cost_ratio: float = 1.1
    archive_min_occurrences: int = 5
    archive_min_cost_ratio: float = 1.3
    silence_factor: float = 2.0


def shadow_decide(
    *,
    state: str,
    evidence: Evidence,
    thresholds: EngineThresholds,
    image_hash: str,
    oplog: OpLog,
    days_since_last_solicitation: float | None = None,
    trigger_period_days: float | None = None,
) -> str:
    """Evaluate the state machine on lived evidence; log the would-move.

    Returns the decision ("ephemeral" | "pinned" | "trial" | "archived" |
    "hold") and ONLY logs — a shadow engine that writes refs is a live
    engine, which is v2 behind the divergence calibration this log feeds.

    `days_since_last_solicitation` and `trigger_period_days` enable the
    silence-based demotion rule (> silence_factor × period). In v1 these
    are optional — the runtime doesn't track them yet. When supplied, the
    engine evaluates and logs `would: demote_silence`.
    """
    would = "hold"

    # --- silence-based demotion (highest priority, overrides other rules) ---
    if (
        state in ("ephemeral", "pinned")
        and days_since_last_solicitation is not None
        and trigger_period_days is not None
        and trigger_period_days > 0
        and days_since_last_solicitation > thresholds.silence_factor * trigger_period_days
    ):
        would = "trial"
        oplog.emit(
            "tag",
            actor="engine:shadow",
            image=image_hash,
            from_state=state,
            evidence=evidence.model_dump(),
            would="demote_silence",
            silence_days=days_since_last_solicitation,
            silence_threshold=thresholds.silence_factor * trigger_period_days,
        )
        return would

    # --- cost/occurrence-based rules ---
    if (
        state == "trial"
        and evidence.occurrences >= thresholds.promote_min_occurrences
        and evidence.cost_ratio <= thresholds.promote_max_cost_ratio
    ):
        would = "ephemeral"
    elif (
        state == "ephemeral"
        and evidence.occurrences >= thresholds.pin_min_solicitations
        and evidence.cost_ratio <= thresholds.pin_max_cost_ratio
    ):
        would = "pinned"
    elif (
        state in ("ephemeral", "pinned")
        and evidence.occurrences >= thresholds.demote_min_occurrences
        and evidence.cost_ratio >= thresholds.demote_min_cost_ratio
    ):
        # Demotion: pinned regresses to ephemeral, ephemeral regresses to trial.
        would = "ephemeral" if state == "pinned" else "trial"
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

