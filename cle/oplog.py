"""One JSON line per operation — the single emitter for invariant 4.

CLE need: every lifecycle op logs one JSON line (invariant 4, BLUEPRINT §5)
and
those lines are a deliverable (the article-9 raw material). One emitter,
used by every module, keeps the format from drifting; the format itself is
specified in the cle-core-contracts skill:

  {"op":"build|run|tag|revalidate|topology_write", "ts":"iso8601",
   "actor":"human:<id>|engine:shadow|engine:live", "image":"<hash8>",
   "from":"<state?>","to":"<state?>",
   "evidence":{...}|"pre_evidence":{...}|"persistence":{...},
   "latency_ms":n}

Upward tag moves REQUIRE `evidence`. Builds carry `pre_evidence`.
Re-validations carry `persistence`. Ops outside the tag/build family
(integrity_violation, detector_observing) carry op/ts/actor plus their own
context keys.

This module is NOT in the BLUEPRINT §2 layout; its existence is justified
by invariant 4 alone, not by any borrowed vocabulary.
"""

import json
import sys
from datetime import datetime, timezone
from typing import Any, TextIO


class OpLog:
    """Writes one self-contained JSON line per operation to a sink.

    The sink is injected so tests capture lines in memory and the CLI can
    direct them to a file; default is stderr so no op is ever silent.
    """

    def __init__(self, sink: TextIO | None = None) -> None:
        self._sink = sink if sink is not None else sys.stderr

    def emit(
        self,
        op: str,
        *,
        actor: str,
        on_behalf_of: str | None = None,
        image: str | None = None,
        from_state: str | None = None,
        to_state: str | None = None,
        evidence: dict[str, Any] | None = None,
        pre_evidence: dict[str, Any] | None = None,
        persistence: dict[str, Any] | None = None,
        latency_ms: float | None = None,
        **context: Any,
    ) -> None:
        # Key order mirrors the contract format; json.dumps preserves
        # insertion order, so the emitted line reads like the spec.
        record: dict[str, Any] = {
            "op": op,
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
        }
        # Provenance, sitting next to the actor it qualifies: `actor` says WHO
        # acted, `on_behalf_of` says FOR WHOM. Required on decision ops tied to
        # a specific workspace or user (see requires_on_behalf_of); omitted on
        # purely technical ops, where the question has no meaning.
        if on_behalf_of is not None:
            record["on_behalf_of"] = on_behalf_of
        if image is not None:
            record["image"] = image[:8]  # <hash8> per the contract
        if from_state is not None:
            record["from"] = from_state
        if to_state is not None:
            record["to"] = to_state
        if evidence is not None:
            record["evidence"] = evidence
        if pre_evidence is not None:
            record["pre_evidence"] = pre_evidence
        if persistence is not None:
            record["persistence"] = persistence
        if latency_ms is not None:
            record["latency_ms"] = latency_ms
        reserved_collisions = record.keys() & context.keys()
        if reserved_collisions:
            raise ValueError(f"context keys shadow contract keys: {reserved_collisions}")
        record.update(context)
        self._sink.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── two READ views over the one write path ──────────────────────────────────
# CLE need: the log serves two readers with opposite needs. An operator
# debugging wants every mechanical step; a human auditing article-9 wants only
# the moments where something was DECIDED. Splitting them is a READ concern —
# there is still exactly one writer (OpLog.emit), no duplication, and no new
# call site. Invariant 4 is untouched.

TECHNICAL_OPS = frozenset({
    "build", "run", "switch", "integrity_violation", "detector_observing",
    "closure_distribution", "cluster_stability",
    # A revalidation that HELD decided nothing — the check merely ran. Only its
    # failing twin (revalidation_failed) carries a consequence.
    "revalidate",
})

DECISION_OPS = frozenset({
    "tag",                  # promote / demote / archive / resurrect, and approve
    "revalidation_failed",  # proof expired -> auto-demote
    "topology_write",
    "candidate_declined",   # decline
})


class UnclassifiedOpError(KeyError):
    """An op belongs to neither view. Deliberately loud: a new operation must
    be classified in the same change that introduces it, or the decision view
    silently drops it and the audit trail is incomplete."""


def classify_op(op: str) -> str:
    """"technical" | "decision" — exactly one, never both."""
    if op in DECISION_OPS:
        return "decision"
    if op in TECHNICAL_OPS:
        return "technical"
    raise UnclassifiedOpError(
        f"op {op!r} is in neither TECHNICAL_OPS nor DECISION_OPS; classify it "
        "in cle/oplog.py in the same change that emits it"
    )


def requires_on_behalf_of(record: dict[str, Any]) -> bool:
    """Is "for whom did this happen" a meaningful question for this line?

    Only for DECISION ops naming a specific subject (an agent or a workspace).
    Technical ops are excluded by design; `run`/`switch` already carry
    `workspace`, which IS their on-behalf-of — aliased, never duplicated.
    """
    if classify_op(record.get("op", "")) != "decision":
        return False
    return bool(record.get("agent") or record.get("image") or record.get("workspace"))


def _subject(record: dict[str, Any]) -> str:
    return record.get("agent") or record.get("image") or record.get("workspace") or "?"


def render_decision(record: dict[str, Any]) -> str:
    """One readable sentence for a decision line: actor + verb + subject +
    evidence. The raw JSON stays available in the technical view; this is the
    audit reading, not a replacement."""
    actor, subject = record.get("actor", "?"), _subject(record)
    op = record.get("op", "?")
    on_behalf = f" on behalf of {record['on_behalf_of']}" if record.get("on_behalf_of") else ""

    if op == "tag":
        frm, to = record.get("from"), record.get("to")
        # The shadow engine emits a `tag` line that moves NOTHING — it carries
        # `would` and no `to`. Rendering it as a move would put a decision in
        # the audit trail that never happened.
        if record.get("would") is not None:
            return (f"{actor}{on_behalf} judged {subject} from {frm} — "
                    f"would: {record['would']} (no ref written)")
        verb = "moved" if frm else "tagged"
        where = f"{frm} -> {to}" if frm else str(to)
        why = ""
        if record.get("evidence"):
            e = record["evidence"]
            why = f" (evidence: {e.get('occurrences')} occurrences at cost {e.get('cost_ratio')})"
        elif record.get("pre_evidence"):
            pe = record["pre_evidence"]
            why = f" (pre_evidence: capture {pe.get('capture_rate')}, false {pe.get('false_trigger_rate')})"
        if record.get("reason"):
            why += f" — {record['reason']}"
        return f"{actor}{on_behalf} {verb} {subject} {where}{why}"

    if op == "candidate_declined":
        why = f" — {record['reason']}" if record.get("reason") else ""
        return f"{actor}{on_behalf} declined {subject} (was {record.get('from', '?')}){why}"

    if op == "revalidation_failed":
        pers = record.get("persistence") or {}
        moved = len(pers.get("probe_deltas") or ())
        return (f"{actor}{on_behalf} expired the proof of {subject} "
                f"({moved} probe(s) moved) -> demoted to trial")

    if op == "topology_write":
        return (f"{actor}{on_behalf} wrote topology v{record.get('version', '?')} "
                f"— {subject} now {record.get('to', '?')} (diff {record.get('diff_size', '?')})")

    return f"{actor}{on_behalf} {op} {subject}"
