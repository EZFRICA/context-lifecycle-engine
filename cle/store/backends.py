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

import json
import re
import sqlite3
from pathlib import Path
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


class FileStore:
    """Directory-backed store: objects/<hash> files plus refs.json.

    CLE need: the lifecycle spans CLI invocations and days — evidence
    accumulates against artifacts that must outlive a process. Same
    Protocol as InMemoryStore; tests use tmp_path, never a server.
    (P2 decision, documented: this is the persistence the CLI runs on;
    WeaviateStore remains the deferred remote backend.)
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._objects_dir = self._root / "objects"
        self._objects_dir.mkdir(parents=True, exist_ok=True)
        self._refs_path = self._root / "refs.json"

    def _read_refs(self) -> dict[str, str]:
        if not self._refs_path.exists():
            return {}
        return json.loads(self._refs_path.read_text())

    def _write_refs(self, refs: dict[str, str]) -> None:
        self._refs_path.write_text(json.dumps(refs, indent=1, sort_keys=True))

    def put(self, object_hash: str, data: bytes) -> None:
        if content_hash(data) != object_hash:
            raise ValueError(f"content does not hash to requested address {object_hash[:8]}")
        (self._objects_dir / object_hash).write_bytes(data)

    def get(self, object_hash: str) -> bytes:
        path = self._objects_dir / object_hash
        if not path.exists():
            raise KeyError(object_hash)
        return path.read_bytes()

    def move_ref(self, name: str, object_hash: str) -> None:
        refs = self._read_refs()
        assert_ref_movable(name, refs)
        refs[name] = object_hash
        self._write_refs(refs)

    def list_refs(self, prefix: str) -> list[tuple[str, str]]:
        return sorted(
            (name, target) for name, target in self._read_refs().items() if name.startswith(prefix)
        )

    def snapshot(self) -> tuple[dict[str, bytes], dict[str, str]]:
        objects = {p.name: p.read_bytes() for p in self._objects_dir.iterdir()}
        return objects, self._read_refs()


class SqliteStore:
    """SQLite-backed store — determinism beyond InMemory, one inspectable file.

    CLE need: the lifecycle persists across processes and must be
    INSPECTABLE (the GDG use case and full_loop run on it); stdlib
    sqlite3, zero network, deterministic — eligible for the default test
    suite. Weaviate remains the deferred remote/vector backend behind the
    integration marker. Same Protocol, same shared ref rule.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self._path))
        self._db.execute("CREATE TABLE IF NOT EXISTS objects (hash TEXT PRIMARY KEY, data BLOB)")
        self._db.execute("CREATE TABLE IF NOT EXISTS refs (name TEXT PRIMARY KEY, target TEXT)")
        self._db.commit()

    def put(self, object_hash: str, data: bytes) -> None:
        if content_hash(data) != object_hash:
            raise ValueError(f"content does not hash to requested address {object_hash[:8]}")
        self._db.execute(
            "INSERT OR REPLACE INTO objects (hash, data) VALUES (?, ?)", (object_hash, data)
        )
        self._db.commit()

    def get(self, object_hash: str) -> bytes:
        row = self._db.execute(
            "SELECT data FROM objects WHERE hash = ?", (object_hash,)
        ).fetchone()
        if row is None:
            raise KeyError(object_hash)
        return bytes(row[0])

    def move_ref(self, name: str, object_hash: str) -> None:
        refs = dict(self._db.execute("SELECT name, target FROM refs").fetchall())
        assert_ref_movable(name, refs)
        self._db.execute(
            "INSERT OR REPLACE INTO refs (name, target) VALUES (?, ?)", (name, object_hash)
        )
        self._db.commit()

    def list_refs(self, prefix: str) -> list[tuple[str, str]]:
        rows = self._db.execute(
            "SELECT name, target FROM refs WHERE name LIKE ? ORDER BY name", (prefix + "%",)
        ).fetchall()
        return [(name, target) for name, target in rows]

    def snapshot(self) -> tuple[dict[str, bytes], dict[str, str]]:
        objects = {
            h: bytes(d) for h, d in self._db.execute("SELECT hash, data FROM objects").fetchall()
        }
        refs = dict(self._db.execute("SELECT name, target FROM refs").fetchall())
        return objects, refs

    def close(self) -> None:
        self._db.close()
