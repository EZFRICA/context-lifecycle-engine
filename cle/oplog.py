"""One JSON line per operation — the single emitter for invariant 4.

CLE need: every lifecycle op logs one JSON line (CLAUDE.md invariant 4) and
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
