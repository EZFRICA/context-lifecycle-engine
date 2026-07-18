"""Storage backend Protocol and implementations.

Contract (cle-core-contracts):
- Protocol: `put(hash, bytes)`, `get(hash)`, `move_ref(name, hash)`,
  `list_refs(prefix)`.
- Refs: `agents/<name>/<state>` (mobile), `agents/<name>/v<semver>`
  (immutable — moving one raises), `topology/<version>`.
- Semver rule (applied by P3 tagging, recorded here): major = trigger
  changed, minor = component ref swapped, patch = lifecycle thresholds only.
- `InMemoryStore` is the default and the only test dependency. WeaviateStore
  (client v4) mirrors the Protocol; integration-tested separately — no unit
  or property test may import it.
"""

import re
from typing import Protocol, runtime_checkable

from cle.store.objects import content_hash

# agents/<name>/v<semver> — these refs are immutable once created.
# Deliberately the core triplet only: the contract's semver rule defines
# major/minor/patch semantics and nothing else, so prerelease/build refs
# are not a namespace we mint (a decision, not an oversight).
_VERSION_REF = re.compile(r"^agents/.+/v\d+\.\d+\.\d+$")


class ImmutableRefError(Exception):
    """An `agents/<name>/v<semver>` ref already exists and cannot move."""


def assert_ref_movable(name: str, current_refs: dict[str, str]) -> None:
    """Shared ref rule for every backend — version refs are write-once.

    CLE need: an immutable version is the thing evidence accumulated
    against; silently re-pointing it would forge history.
    """
    if _VERSION_REF.match(name) and name in current_refs:
        raise ImmutableRefError(f"version ref {name} is immutable once created")


@runtime_checkable
class StoreBackend(Protocol):
    def put(self, object_hash: str, data: bytes) -> None: ...

    def get(self, object_hash: str) -> bytes: ...

    def move_ref(self, name: str, object_hash: str) -> None: ...

    def list_refs(self, prefix: str) -> list[tuple[str, str]]: ...


class InMemoryStore:
    """Default backend; the only one tests may depend on."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self._refs: dict[str, str] = {}

    def put(self, object_hash: str, data: bytes) -> None:
        # The store never willingly holds mislabeled data: an address that
        # doesn't match its content is rejected at the door.
        if content_hash(data) != object_hash:
            raise ValueError(f"content does not hash to requested address {object_hash[:8]}")
        self._objects[object_hash] = data

    def get(self, object_hash: str) -> bytes:
        return self._objects[object_hash]

    def move_ref(self, name: str, object_hash: str) -> None:
        assert_ref_movable(name, self._refs)
        self._refs[name] = object_hash

    def list_refs(self, prefix: str) -> list[tuple[str, str]]:
        return sorted(
            (name, target) for name, target in self._refs.items() if name.startswith(prefix)
        )

    def snapshot(self) -> tuple[dict[str, bytes], dict[str, str]]:
        """Copy of all state — for the staged-failure-writes-nothing
        byte-compare (BLUEPRINT §8 test floor); not part of the Protocol."""
        return dict(self._objects), dict(self._refs)
