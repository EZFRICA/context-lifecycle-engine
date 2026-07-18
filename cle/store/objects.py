"""Content hashing and stored blocks.

Contract (cle-core-contracts):
- `content_hash(obj) -> str` is THE hashing function — canonical JSON
  (sorted keys, no whitespace, UTF-8), sha256 hexdigest. Never inline
  hashlib elsewhere in the codebase.
- Every component fetched from a backend is re-hashed against the requested
  hash before use. Mismatch triggers the integrity protocol: abort use, log
  {"op":"integrity_violation",...}, refetch; never crash, never silently
  inject a corrupt component.
"""

import hashlib
import json
from typing import Any, Protocol

from pydantic import BaseModel

from cle.oplog import OpLog


def content_hash(obj: Any) -> str:
    """Hash any storable value into its content address.

    bytes are hashed as-is — backends store canonical encodings, and
    verify-on-read must reproduce the address from the stored bytes without
    a decode/re-encode round trip. Everything else is canonicalized first:
    pydantic models via model_dump, then canonical JSON (sorted keys, no
    whitespace, UTF-8).
    """
    if isinstance(obj, bytes):
        data = obj
    else:
        if isinstance(obj, BaseModel):
            obj = obj.model_dump(mode="json")
        data = _canonical_json_bytes(obj)
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


class Block(BaseModel, frozen=True):
    """A content-addressed component a candidate's #refs resolve to.

    CLE need (BLUEPRINT §3, stage 1): the resolve stage looks refs up by exact
    content, so components must carry a stable address derived from nothing
    but their content. `kind` records what the payload is (prompt fragment,
    memory block, ...) so assembly can order and label components.
    """

    kind: str
    payload: str

    def canonical_bytes(self) -> bytes:
        """The exact encoding a backend stores — hashing it yields self.hash."""
        return _canonical_json_bytes(self.model_dump(mode="json"))

    @property
    def hash(self) -> str:
        return content_hash(self)


class _ReadableBackend(Protocol):
    # Structural view of the store Protocol (backends.py, commit 3) — the
    # integrity check only ever needs the read path.
    def get(self, requested_hash: str) -> bytes: ...


class IntegrityError(Exception):
    """A component failed verification twice; the operation must abort.

    Raised as a typed, catchable failure (the build treats it as a failed
    resolve that writes nothing) — "never crash" means no uncontrolled
    process death, not that corruption is survivable.
    """


def fetch_verified(backend: _ReadableBackend, requested_hash: str, oplog: OpLog) -> bytes:
    """Fetch a component and re-hash it against the requested address.

    Mismatch -> integrity protocol: log the violation, refetch once (the
    corruption may be transport-level, not storage-level), and if the
    second copy is also bad, raise. The corrupt bytes are never returned.
    """
    data = backend.get(requested_hash)
    if content_hash(data) == requested_hash:
        return data

    oplog.emit("integrity_violation", actor="system:store", component=requested_hash[:8])
    refetched = backend.get(requested_hash)
    if content_hash(refetched) == requested_hash:
        return refetched

    oplog.emit(
        "integrity_violation",
        actor="system:store",
        component=requested_hash[:8],
        refetch="failed",
    )
    raise IntegrityError(f"component {requested_hash[:8]} failed verification after refetch")
