"""Snapshot builders — read-only views over the FileStore + oplog.

Every function here imports CLE's own read helpers so the dashboard sees
exactly what the engine sees. Nothing here writes. Integrity checks during
reads log to a throwaway sink (the CLI is the authority on the real log).
"""

import io
import json
from pathlib import Path
from typing import Any

from cle.lifecycle.topology import current_agents, latest_version
from cle.oplog import OpLog
from cle.runtime.container import load_containers, load_image
from cle.runtime.metrics_volume import read_events
from cle.store.backends import FileStore

_VOID = OpLog(io.StringIO())  # reads never pollute the real oplog


def store(state_dir: Path) -> FileStore:
    return FileStore(state_dir / "store")


def _short(h: str | None) -> str | None:
    return f"{h[:8]}…" if h else None


def _image_view(backend: FileStore, image_hash: str) -> dict[str, Any]:
    """Public image facts for a card: pre_evidence, trigger, probe count."""
    try:
        image = load_image(backend, image_hash, _VOID)
    except Exception:
        return {"hash": image_hash, "short": _short(image_hash), "missing": True}
    period = image.trigger.period.interval.total_seconds() if image.trigger.period else None
    return {
        "hash": image_hash,
        "short": _short(image_hash),
        "source_hash": image.source_hash,
        "source_short": _short(image.source_hash),
        "model_fingerprint": image.model_fingerprint,
        "fingerprint_short": _short(image.model_fingerprint),
        "probe_count": len(image.probe_set),
        "trigger_period_seconds": period,
        "pre_evidence": image.pre_evidence.model_dump(),
    }


def image_detail(state_dir: Path, image_hash: str) -> dict[str, Any]:
    """Everything a modal wants: the compiled prompt, resolved components,
    frozen probe set, the full trigger, and all of pre_evidence."""
    backend = store(state_dir)
    try:
        image = load_image(backend, image_hash, _VOID)
    except Exception as error:
        return {"hash": image_hash, "short": _short(image_hash), "error": str(error)}
    period = image.trigger.period.interval.total_seconds() if image.trigger.period else None
    return {
        "hash": image.hash,
        "short": _short(image.hash),
        "source_hash": image.source_hash,
        "source_short": _short(image.source_hash),
        "model_fingerprint": image.model_fingerprint,
        "fingerprint_short": _short(image.model_fingerprint),
        "assembled_prompt": image.assembled_prompt,
        "resolved_refs": image.resolved_refs,
        "probe_set": list(image.probe_set),
        "probe_count": len(image.probe_set),
        "trigger_dims": len(image.trigger.centroid),
        "trigger_period_seconds": period,
        "pre_evidence": image.pre_evidence.model_dump(),
    }


def ps(state_dir: Path) -> list[dict[str, Any]]:
    """Running containers with per-container metrics (the human's window)."""
    rows: list[dict[str, Any]] = []
    for workspace, container in sorted(load_containers(state_dir).items()):
        events = read_events(state_dir, container.metrics_volume_id)
        solicitations = sum(1 for e in events if e.get("kind") == "solicitation")
        iterations = sum(e.get("count", 0) for e in events if e.get("kind") == "iterations")
        closures: dict[str, int] = {}
        for event in events:
            if event.get("kind") == "closure":
                tag = event.get("tag", "unknown")
                closures[tag] = closures.get(tag, 0) + 1
        rows.append(
            {
                "workspace": workspace,
                "image": container.image_hash,
                "image_short": _short(container.image_hash),
                "metrics": {
                    "solicitations": solicitations,
                    "iterations": iterations,
                    "closures": closures,
                },
            }
        )
    return rows


def candidates(state_dir: Path) -> list[dict[str, Any]]:
    """The proposal menu: agents currently in the `candidate` state."""
    backend = store(state_dir)
    out: list[dict[str, Any]] = []
    for name, entry in sorted(current_agents(backend).items()):
        if entry.get("state") != "candidate":
            continue
        out.append(
            {
                "agent": name,
                "state": entry["state"],
                "since": entry.get("since"),
                "image": _image_view(backend, entry["image"]),
            }
        )
    return out


def images(state_dir: Path) -> list[dict[str, Any]]:
    """All agents with their current lifecycle state + image + version refs."""
    backend = store(state_dir)
    versions: dict[str, list[str]] = {}
    for ref_name, target in backend.list_refs("agents/"):
        parts = ref_name.split("/")
        if len(parts) == 3 and parts[2].startswith("v"):
            versions.setdefault(target, []).append(parts[2])
    out: list[dict[str, Any]] = []
    for name, entry in sorted(current_agents(backend).items()):
        view = _image_view(backend, entry["image"])
        out.append(
            {
                "agent": name,
                "state": entry["state"],
                "since": entry.get("since"),
                "versions": sorted(versions.get(entry["image"], [])),
                "image": view,
            }
        )
    return out


def _topology_record(backend: FileStore, version: int) -> dict[str, Any] | None:
    ref = f"topology/v{version}"
    refs = dict(backend.list_refs("topology/v"))
    if ref not in refs:
        return None
    return json.loads(backend.get(refs[ref]))


def topology_versions(state_dir: Path) -> list[int]:
    backend = store(state_dir)
    return sorted(int(name.split("/v")[1]) for name, _ in backend.list_refs("topology/v"))


def topology(state_dir: Path, version: int | None = None) -> dict[str, Any]:
    """One topology version as a graph-ready payload."""
    backend = store(state_dir)
    if version is None:
        version_number, record = latest_version(backend)
    else:
        record = _topology_record(backend, version)
        version_number = version
    if not record:
        return {"version": 0, "agents": {}, "nodes": [], "edges": []}
    agents = record.get("agents", {})
    nodes = [
        {
            "agent": name,
            "state": entry.get("state"),
            "image_short": _short(entry.get("image")),
            "cause_kind": _cause_kind(entry.get("cause", {})),
        }
        for name, entry in sorted(agents.items())
    ]
    return {
        "version": version_number,
        "parent": record.get("parent"),
        "actor": record.get("actor"),
        "agents": agents,
        "nodes": nodes,
    }


def _cause_kind(cause: dict[str, Any]) -> str:
    for kind in ("evidence", "pre_evidence", "persistence", "reason"):
        if kind in cause:
            return kind
    return "?"


def topology_diff(state_dir: Path, a: int, b: int) -> dict[str, Any]:
    """Structured delta between two topology versions, with each entry's
    evidence — added / removed / retagged."""
    backend = store(state_dir)
    rec_a, rec_b = _topology_record(backend, a), _topology_record(backend, b)
    if rec_a is None or rec_b is None:
        raise KeyError("unknown topology version")
    agents_a, agents_b = rec_a.get("agents", {}), rec_b.get("agents", {})
    changes: list[dict[str, Any]] = []
    for agent in sorted(set(agents_a) | set(agents_b)):
        ea, eb = agents_a.get(agent), agents_b.get(agent)
        if ea == eb:
            continue
        if ea is None:
            changes.append(
                {"kind": "added", "agent": agent, "to_state": eb["state"],
                 "cause_kind": _cause_kind(eb.get("cause", {})), "cause": eb.get("cause", {})}
            )
        elif eb is None:
            changes.append({"kind": "removed", "agent": agent, "from_state": ea["state"]})
        else:
            changes.append(
                {"kind": "retagged", "agent": agent, "from_state": ea["state"],
                 "to_state": eb["state"], "cause_kind": _cause_kind(eb.get("cause", {})),
                 "cause": eb.get("cause", {})}
            )
    return {"a": a, "b": b, "changes": changes}
