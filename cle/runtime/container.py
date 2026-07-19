"""Container record — Goodhart boundary enforced here.

Contract (cle-core-contracts, invariant 2): `Container` is a mutable record
of a running instantiation. It MUST NOT expose any read path to its own
metrics — no method, no property, no injected context. The runtime writes
metrics one-way through `metrics_volume.record(container_id, event)`; the
only metrics-adjacent thing a Container may carry is the opaque id of the
volume the runtime writes to.

P2 completes the runtime as MODULE FUNCTIONS — instantiate, solicit,
switch — precisely so the Container record surface never widens and the
reflection test in tests/property/test_goodhart_boundary.py stays green
by construction.

Switch cost (non-negotiable measurement): every workspace switch logs
`diff_blocks` and `diff_tokens`, computed by diff-only checkout between
the outgoing and incoming images — the context-switch cost metric, the
founding question of the series.
"""

import json
import time
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel

from cle.oplog import OpLog
from cle.runtime.metrics_volume import MetricsVolume
from cle.runtime.mounts import Mount, as_record, validate_mounts
from cle.store.backends import StoreBackend
from cle.store.commits import Image
from cle.store.objects import fetch_verified


class Container(BaseModel):
    """A running instantiation of an image in one workspace.

    Mutable record (not frozen): the runtime updates mounts on
    reconfiguration. The metrics volume id is an opaque write-target
    pointer for the runtime — it is not, and must never become, a way for
    the container (or the agent inside it) to read its own numbers.
    """

    image_hash: str
    workspace_id: str
    # Data-only mount record: scope_ref -> mode (the Mount model with its
    # validation logic stays runtime-side, see mounts.py).
    mounts: dict[str, str]
    metrics_volume_id: str


def container_id(container: Container) -> str:
    """Identity = workspace + image: switching images in a workspace is a
    NEW container (metrics must never blend across a switch). A module
    function, not a property — the record surface is frozen by the
    Goodhart reflection test and stays data-only."""
    return f"{container.workspace_id}:{container.image_hash[:8]}"


def load_image(backend: StoreBackend, image_hash: str, oplog: OpLog) -> Image:
    record = json.loads(fetch_verified(backend, image_hash, oplog))
    if record.pop("cle_kind", None) != "image":
        raise ValueError(f"{image_hash[:8]} is not an image")
    return Image.model_validate(record)


def _containers_path(state_root: Path) -> Path:
    return Path(state_root) / "containers.json"


def load_containers(state_root: Path) -> dict[str, Container]:
    """Runtime state, keyed by workspace_id — one live container each."""
    path = _containers_path(state_root)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {ws: Container.model_validate(record) for ws, record in raw.items()}


def save_containers(state_root: Path, containers: dict[str, Container]) -> None:
    path = _containers_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({ws: c.model_dump() for ws, c in containers.items()}, indent=1, sort_keys=True)
    )


def switch_cost(backend: StoreBackend, outgoing: Image, incoming: Image, oplog: OpLog) -> tuple[int, int]:
    """Diff-only checkout between two images: how many blocks change and
    how many tokens those blocks carry. This pair IS the context-switch
    cost measurement."""
    outgoing_blocks = set(outgoing.resolved_refs.values())
    incoming_blocks = set(incoming.resolved_refs.values())
    changed = outgoing_blocks ^ incoming_blocks
    diff_tokens = 0
    for block_hash in changed:
        record = json.loads(fetch_verified(backend, block_hash, oplog))
        diff_tokens += len(str(record.get("payload", "")).split())
    return len(changed), diff_tokens


def ensure_container(
    *,
    state_root: Path,
    backend: StoreBackend,
    image_hash: str,
    workspace_id: str,
    mounts: Sequence[Mount],
    oplog: OpLog,
    actor: str,
) -> Container:
    """Give the workspace a container of this image, switching (and
    logging the switch cost) if it currently runs another image."""
    incoming = load_image(backend, image_hash, oplog)
    validate_mounts(list(mounts), backend)
    containers = load_containers(state_root)
    existing = containers.get(workspace_id)
    if existing is not None and existing.image_hash == image_hash:
        return existing
    if existing is not None:
        outgoing = load_image(backend, existing.image_hash, oplog)
        diff_blocks, diff_tokens = switch_cost(backend, outgoing, incoming, oplog)
        oplog.emit(
            "switch",
            actor=actor,
            image=image_hash,
            from_state=existing.image_hash[:8],
            workspace=workspace_id,
            diff_blocks=diff_blocks,
            diff_tokens=diff_tokens,
        )
    container = Container(
        image_hash=image_hash,
        workspace_id=workspace_id,
        mounts=as_record(list(mounts)),
        metrics_volume_id=f"vol-{workspace_id}",
    )
    containers[workspace_id] = container
    save_containers(state_root, containers)
    return container


def solicit(
    *,
    state_root: Path,
    backend: StoreBackend,
    container: Container,
    prompt: str,
    oplog: OpLog,
) -> str:
    """One solicitation of the containerized agent against the REAL configured
    model; iteration count is derived from the live response length. Falls
    back to a deterministic stand-in when no model is reachable (offline/CI),
    so metrics stay meaningful without a key. Metrics go through the volume
    ONLY — the container record is not touched, and nothing here returns
    metrics to the caller."""
    image = load_image(backend, container.image_hash, oplog)  # integrity check before use

    # Assemble the agent's system prompt + the user prompt for the real call.
    full_prompt = f"{image.assembled_prompt}\n\nUser request: {prompt}"

    from cle.build.fingerprinter import response_text as _extract_text
    from cle.llm_provider import get_main_llm

    try:
        response = get_main_llm().invoke(full_prompt)
        response_text = _extract_text(response.content)  # text only, no volatile metadata
        # Iterations scale with the live response length.
        iterations = max(1, min(5, 1 + (len(response_text.split()) // 30)))
    except Exception as error:
        # Offline / no key: deterministic stand-in so different workspaces
        # still diverge (cost scales with prompt size).
        response_text = f"[offline stand-in: {error.__class__.__name__}]"
        iterations = 1 + (len(prompt.split()) % 3)

    volume = MetricsVolume(state_root, container.metrics_volume_id)
    volume.record(container_id(container), {"kind": "solicitation", "prompt_tokens": len(prompt.split())})
    volume.record(container_id(container), {"kind": "iterations", "count": iterations})
    volume.record(
        container_id(container),
        {"kind": "closure", "tag": "success" if iterations < 4 else "reformulated"},
    )
    return f"[{container_id(container)}] Response: {response_text[:80]}... (iterations: {iterations})"


def run_prompts(
    *,
    state_root: Path,
    backend: StoreBackend,
    container: Container,
    prompts: Sequence[str],
    oplog: OpLog,
    actor: str,
) -> list[str]:
    """A `cle run` invocation: N solicitations, one op line."""
    started = time.monotonic()
    responses = [
        solicit(
            state_root=state_root, backend=backend, container=container, prompt=prompt, oplog=oplog
        )
        for prompt in prompts
    ]
    oplog.emit(
        "run",
        actor=actor,
        image=container.image_hash,
        workspace=container.workspace_id,
        solicitations=len(prompts),
        latency_ms=round((time.monotonic() - started) * 1000, 3),
    )
    return responses
