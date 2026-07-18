"""Container record — Goodhart boundary enforced here.

Contract (cle-core-contracts, invariant 2): `Container` is a mutable record
of a running instantiation. It MUST NOT expose any read path to its own
metrics — no method, no property, no injected context. The runtime writes
metrics one-way through `metrics_volume.record(container_id, event)`; the
only metrics-adjacent thing a Container may carry is the opaque id of the
volume the runtime writes to.

P1 ships this record as a stub guarded by the reflection test in
tests/property/test_goodhart_boundary.py; P2 adds runtime behavior WITHOUT
widening this surface.
"""

from pydantic import BaseModel


class Container(BaseModel):
    """A running instantiation of an image in one workspace.

    Mutable record (not frozen): the runtime updates mounts on
    reconfiguration. The metrics volume id is an opaque write-target
    pointer for the runtime — it is not, and must never become, a way for
    the container (or the agent inside it) to read its own numbers.
    """

    image_hash: str
    workspace_id: str
    # P2 refines mount scopes (ro/rw, MCP handles); P1 keeps the shape only.
    mounts: dict[str, str]
    metrics_volume_id: str
