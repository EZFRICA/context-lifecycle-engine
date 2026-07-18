"""topology.yaml writer — sole author of the topology file.

Contract (BLUEPRINT §7): every change is a commit in the same DAG under
the `topology/` ref prefix (one store, one audit trail). Entries carry
the evidence (or pre_evidence at birth) that caused them. `cle log
topology.yaml` renders the history with provenance and numbers; `cle
diff` renders the learned-topology delta. Diff size per version is a
deliverable measurement (logged on every write).

Version refs are `topology/v<n>`, n monotonically increasing; each
version object records its parent hash, so the chain is walkable without
trusting ref order.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from cle.oplog import OpLog
from cle.store.backends import StoreBackend
from cle.store.objects import content_hash


def _canonical(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def latest_version(backend: StoreBackend) -> tuple[int, dict | None]:
    refs = backend.list_refs("topology/v")
    if not refs:
        return 0, None
    number = max(int(name.split("/v")[1]) for name, _ in refs)
    target = dict(refs)[f"topology/v{number}"]
    return number, json.loads(backend.get(target))


def current_agents(backend: StoreBackend) -> dict[str, dict[str, Any]]:
    """The live agent index (name -> {state, image, since}) from the
    latest topology version — the lifecycle's source of truth."""
    _, latest = latest_version(backend)
    return dict(latest["agents"]) if latest else {}


def write_topology(
    *,
    backend: StoreBackend,
    path: Path,
    agent: str,
    state: str,
    image_hash: str,
    cause: dict[str, Any],
    oplog: OpLog,
    actor: str,
) -> str:
    """Record one agent change as a new topology version + file rewrite.

    `cause` is the evidence/pre_evidence payload (with its kind) that
    justified the change — a topology entry without proof is exactly the
    prediction-driven drift the CLE exists to refuse.
    """
    started = time.monotonic()
    # Decision (documented): downward moves may carry a bare human reason
    # — evidence justifies gains; losses need accountability, not proof.
    if not cause or not any(
        k in cause for k in ("evidence", "pre_evidence", "persistence", "reason")
    ):
        raise ValueError("topology change requires an evidence-bearing cause (or a reason)")

    version_number, latest = latest_version(backend)
    agents = dict(latest["agents"]) if latest else {}
    previous_entry = agents.get(agent)
    agents[agent] = {
        "state": state,
        "image": image_hash,
        "since": datetime.now(timezone.utc).isoformat(),
        "cause": cause,
    }
    record = {
        "cle_kind": "topology",
        "version": version_number + 1,
        "parent": (
            dict(backend.list_refs(f"topology/v{version_number}")).get(
                f"topology/v{version_number}"
            )
            if version_number
            else None
        ),
        "actor": actor,
        "agents": agents,
    }
    data = _canonical(record)
    record_hash = content_hash(data)
    backend.put(record_hash, data)
    backend.move_ref(f"topology/v{record['version']}", record_hash)

    # The visible artifact humans read; the store chain is the authority.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"version": record["version"], "agents": agents}, sort_keys=True, width=100
        )
    )
    # diff_size compares the durable half of the entry (state/image/cause);
    # `since` is a timestamp and would make every write look like a change.
    def _durable(entry: dict | None) -> dict | None:
        return {k: v for k, v in entry.items() if k != "since"} if entry else None

    diff_size = 1 if _durable(previous_entry) != _durable(agents[agent]) else 0
    oplog.emit(
        "topology_write",
        actor=actor,
        image=image_hash,
        to_state=state,
        diff_size=diff_size,
        version=record["version"],
        latency_ms=round((time.monotonic() - started) * 1000, 3),
        **{
            k: v
            for k, v in cause.items()
            if k in ("evidence", "pre_evidence", "persistence", "reason")
        },
    )
    return f"topology/v{record['version']}"


def render_log(backend: StoreBackend) -> str:
    """`cle log topology.yaml`: history with provenance and numbers."""
    lines = []
    for name, target in backend.list_refs("topology/v"):
        record = json.loads(backend.get(target))
        for agent, entry in sorted(record["agents"].items()):
            cause = entry.get("cause", {})
            proof_kind = next(
                (k for k in ("evidence", "pre_evidence", "persistence") if k in cause), "?"
            )
            numbers = cause.get(proof_kind, {})
            summary = ", ".join(f"{k}={v}" for k, v in list(numbers.items())[:3])
            lines.append(
                f"{name}  {agent}: {entry['state']}  image={entry['image'][:8]}  "
                f"by={record['actor']}  {proof_kind}({summary})"
            )
    return "\n".join(lines) if lines else "(no topology versions)"


def render_diff(backend: StoreBackend, ref_a: str, ref_b: str) -> str:
    """`cle diff`: the learned-topology delta between two versions."""
    versions = dict(backend.list_refs("topology/v"))
    for ref in (ref_a, ref_b):
        if ref not in versions:
            raise KeyError(f"unknown topology version {ref}")
    agents_a = json.loads(backend.get(versions[ref_a]))["agents"]
    agents_b = json.loads(backend.get(versions[ref_b]))["agents"]
    lines = []
    for agent in sorted(set(agents_a) | set(agents_b)):
        entry_a, entry_b = agents_a.get(agent), agents_b.get(agent)
        if entry_a == entry_b:
            continue
        if entry_a is None:
            lines.append(f"+ {agent}: {entry_b['state']} ({entry_b['image'][:8]})")
        elif entry_b is None:
            lines.append(f"- {agent}: was {entry_a['state']}")
        else:
            lines.append(
                f"~ {agent}: {entry_a['state']}@{entry_a['image'][:8]} -> "
                f"{entry_b['state']}@{entry_b['image'][:8]}"
            )
    return "\n".join(lines) if lines else "(no delta)"
