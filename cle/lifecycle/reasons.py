"""Closed vocabulary for descents and declines — and the boundary free text never crosses.

CLE need (level-2 preparation). A population report must be able to say WHY a
population archives an agent, not only how many. Free text cannot be aggregated,
and — the sharper problem — it carries user content into `topology.yaml`, the
one file level 2 reads. The shape of the leak, on a descent to `archived`:

    cause:
      reason: "Marie du service RH trouve ça trop lent"

A name, in the file destined for population aggregation, on the path that is
level 2's principal signal (an agent's death) and therefore its most-read one.

TWO AXES, TWO TYPE SEPARATIONS — deliberately not one common field:

  * ENGINE vs HUMAN. `substrate_drift` and `silence` are functions of metrics;
    `cost_regression` is a judgement. Aggregating them
    together would blend "the rule fired 300 times" with "300 people decided
    that". Same discipline as the three proof types.
  * DESCENT vs DECLINE. A decline says "the detection was right, the moment was
    not". Counting it as a rejection at population level would be a product
    contresens.

`silence` comes from the CODE: `engine.py` has a `demote_silence` rule, so the
value names something the engine can actually conclude.

Every member of this vocabulary has to name something a code path can actually
conclude. A slot with no producer would let a population report count a cause
the engine is incapable of reaching, which is the kind of unchecked reference
the closed vocabulary exists to forbid, so such a slot is removed rather than
reserved for later.

`engine_disagrees` is kept but MUST stay isolable: it is a human who deferred to
the engine. Aggregating it without being able to exclude it would count the
engine's own influence as an independent human judgement — the Goodhart
constraint at population scale. Hence its own type, never merged into the other
human reasons.

The human/descent box holds a single observed value. It is deliberately not
frozen hard: the corpus will populate it.

NOT a filter, a TYPE. A write-time sanitiser would be bypassed by the next path
someone adds; free text has no *representable* route into a topology record.
"""

from typing import Literal, get_args

from pydantic import BaseModel

# ── the vocabulary, derived from observed values, never a priori ────────────

EngineDemotionReason = Literal["substrate_drift", "silence"]
HumanDemotionReason = Literal["cost_regression"]
HumanDeclineReason = Literal["engine_disagrees", "defer"]

ENGINE_DEMOTION_REASONS = frozenset(get_args(EngineDemotionReason))
HUMAN_DEMOTION_REASONS = frozenset(get_args(HumanDemotionReason))
HUMAN_DECLINE_REASONS = frozenset(get_args(HumanDeclineReason))

#: Every value the closed vocabulary admits, across both axes.
ALL_REASONS = ENGINE_DEMOTION_REASONS | HUMAN_DEMOTION_REASONS | HUMAN_DECLINE_REASONS

#: Reasons authored by the engine — a metric fired, nobody judged.
ENGINE_AUTHORED = ENGINE_DEMOTION_REASONS
#: Reasons authored by a human exercising judgement.
HUMAN_AUTHORED = HUMAN_DEMOTION_REASONS | HUMAN_DECLINE_REASONS
#: Human, but deferring to the engine — isolable so it can be EXCLUDED from any
#: aggregate that claims to measure independent human judgement.
ENGINE_INFLUENCED = frozenset({"engine_disagrees"})


class UnknownReasonError(ValueError):
    """A value outside the closed vocabulary.

    Loud, exactly like `classify_op` on an unknown op, and with no catch-all
    "other": a catch-all would silently absorb the whole distinction this field
    exists to produce.
    """


class FreeTextInTopologyError(ValueError):
    """Something tried to put free text into a topology cause.

    The boundary is structural: a topology record's `reason` is a closed
    vocabulary value, and user prose belongs to the local channel (the oplog
    `note`), which level 2 never reads (invariant 4).
    """


def classify_reason(reason: str) -> str:
    """"engine" | "human" — which side authored this reason. Raises if unknown."""
    if reason in ENGINE_AUTHORED:
        return "engine"
    if reason in HUMAN_AUTHORED:
        return "human"
    raise UnknownReasonError(
        f"reason {reason!r} is outside the closed vocabulary {sorted(ALL_REASONS)}; "
        "add it to cle/lifecycle/reasons.py in the same change that writes it"
    )


def validate_reason(reason: str) -> str:
    """Return the reason if it is in the vocabulary, else raise."""
    classify_reason(reason)  # raises on unknown
    return reason


class TopologyReason(BaseModel, frozen=True):
    """The ONLY shape a reason may take inside a topology record.

    A frozen model over a closed Literal: there is no field able to hold prose,
    so no present or future write path can smuggle user text across the
    boundary. That is the property asked for — not a sanitiser.
    """

    reason: EngineDemotionReason | HumanDemotionReason | HumanDeclineReason

    @property
    def authored_by(self) -> str:
        return classify_reason(self.reason)

    @property
    def engine_influenced(self) -> bool:
        """True for a human decision taken on the engine's advice — excludable
        from any aggregate claiming independent human judgement."""
        return self.reason in ENGINE_INFLUENCED
