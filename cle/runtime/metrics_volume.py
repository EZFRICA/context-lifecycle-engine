"""System-owned metrics volume — the write side of the Goodhart boundary.

Contract (cle-core-contracts, invariant 2): the runtime records
solicitations, iterations, and closure tags via
`record(container_id, event)` — one-way. `MetricsVolume` deliberately has
NO read method: reading belongs to the lifecycle engine and the human via
`read_events`, a module function on the other side of the boundary that
container/agent code never receives. What crosses into a Container is the
volume id string, nothing else.

Storage: one JSONL file per volume under <root>/metrics/, events keyed by
container_id — file-backed for the same reason as FileStore (the
lifecycle outlives a process).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MetricsVolume:
    """Write-only handle the runtime uses while a container runs."""

    def __init__(self, root: Path | str, volume_id: str) -> None:
        self.volume_id = volume_id
        self._path = Path(root) / "metrics" / f"{volume_id}.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, container_id: str, event: dict[str, Any]) -> None:
        stamped = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "container_id": container_id,
            **event,
        }
        with self._path.open("a") as sink:
            sink.write(json.dumps(stamped, ensure_ascii=False) + "\n")


def read_events(
    root: Path | str, volume_id: str, container_id: str | None = None
) -> list[dict[str, Any]]:
    """Engine/human-side read path. Never hand this to container code —
    the reflection test guards the Container surface, this docstring and
    review guard the call sites."""
    path = Path(root) / "metrics" / f"{volume_id}.jsonl"
    if not path.exists():
        return []
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if container_id is not None:
        events = [event for event in events if event["container_id"] == container_id]
    return events
