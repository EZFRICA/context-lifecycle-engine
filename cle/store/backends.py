"""Storage backend Protocol and implementations.

Contract (cle-core-contracts):
- Protocol: `put(hash, bytes)`, `get(hash)`, `move_ref(name, hash)`,
  `list_refs(prefix)`.
- Refs: `agents/<name>/<state>` (mobile), `agents/<name>/v<semver>`
  (immutable - moving one raises), `topology/<version>`.
- Addresses: 64 lowercase hex characters, refused otherwise on both `put` and
  `get` (`assert_object_address`) - an address is an untrusted path component in
  `FileStore` and an untrusted key everywhere else.
- Semver rule (applied by P3 tagging, recorded here): major = trigger
  changed, minor = component ref swapped, patch = lifecycle thresholds only.
Implementations, all behind the same Protocol and all exercised by the
default suite (conformance is parametrized across them):
- `InMemoryStore` - the default, and the only backend the invariant tests need.
- `FileStore` - persistent CLI/dashboard state under `--state-dir`.
- `SqliteStore` - persistent and inspectable; stdlib `sqlite3`, no server.

Both shipped backends are local, offline and deterministic, so both are
eligible for the default suite. There is no remote backend, and no test
depends on an external service.
"""

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Protocol, runtime_checkable

from cle.store.objects import content_hash

# agents/<name>/v<semver> - these refs are immutable once created.
# Deliberately the core triplet only: the contract's semver rule defines
# major/minor/patch semantics and nothing else, so prerelease/build refs
# are not a namespace we mint (a decision, not an oversight).
_VERSION_REF = re.compile(r"^agents/.+/v\d+\.\d+\.\d+$")

#: An object address is a sha-256 hex digest, lowercase, and nothing else.
_OBJECT_ADDRESS = re.compile(r"^[0-9a-f]{64}$")


class ImmutableRefError(Exception):
    """An `agents/<name>/v<semver>` ref already exists and cannot move."""


class InvalidAddressError(ValueError):
    """An object address that is not a sha-256 hex digest.

    A `ValueError` because that is what `put` already raises for an address that
    does not match its content: one refusal kind for "this address is not a
    thing this store will accept".
    """


def assert_object_address(object_hash: str) -> None:
    """Shared address rule for every backend, checked BEFORE the address is used.

    `FileStore` turns an address into a path, so an address is an untrusted path
    component: `../../etc/passwd` read outside the store, and the refusal was a
    `KeyError` that read as "no such object". Measured before this guard, a
    `get("../../witness.txt")` returned the file's 15 bytes.

    Addresses are produced by `content_hash`, so nothing legitimate is refused
    here. What this catches is an address that came from somewhere else: a
    tampered `refs.json`, an HTTP parameter, a corpus field. It is checked on
    every backend rather than only on `FileStore`, because "which backend is
    open" is a runtime setting and a guard that depends on it is not a contract.
    """
    if not _OBJECT_ADDRESS.match(object_hash):
        raise InvalidAddressError(
            f"{object_hash[:16]!r} is not an object address (expected 64 hex "
            "characters). Addresses come from `content_hash`; one that does not "
            "have this shape did not come from the store."
        )


def assert_ref_movable(name: str, current_refs: dict[str, str]) -> None:
    """Shared ref rule for every backend - version refs are write-once.

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
        assert_object_address(object_hash)
        if content_hash(data) != object_hash:
            raise ValueError(f"content does not hash to requested address {object_hash[:8]}")
        self._objects[object_hash] = data

    def get(self, object_hash: str) -> bytes:
        assert_object_address(object_hash)
        return self._objects[object_hash]

    def move_ref(self, name: str, object_hash: str) -> None:
        assert_ref_movable(name, self._refs)
        self._refs[name] = object_hash

    def list_refs(self, prefix: str) -> list[tuple[str, str]]:
        return sorted(
            (name, target) for name, target in self._refs.items() if name.startswith(prefix)
        )

    def snapshot(self) -> tuple[dict[str, bytes], dict[str, str]]:
        """Copy of all state - for the staged-failure-writes-nothing
        byte-compare (BLUEPRINT §8 test floor); not part of the Protocol."""
        return dict(self._objects), dict(self._refs)


class StagedStore:
    """Writes held in memory over a real backend, reaching it only on `commit()`.

    Invariant 3: a staged build consumes nothing. `cle build` seeds the
    components it resolves against, and seeding is a write; done on the real
    store, a build that then failed left blocks and refs behind in a state dir
    it had been refused on. Reads see the pending writes first, then the
    backend beneath; the checks are the backends' own (content address on
    `put`, write-once version refs on `move_ref`, against both layers).
    """

    def __init__(self, backend: StoreBackend) -> None:
        self._backend = backend
        self._pending = InMemoryStore()

    def put(self, object_hash: str, data: bytes) -> None:
        self._pending.put(object_hash, data)

    def get(self, object_hash: str) -> bytes:
        try:
            return self._pending.get(object_hash)
        except KeyError:
            return self._backend.get(object_hash)

    def move_ref(self, name: str, object_hash: str) -> None:
        assert_ref_movable(name, dict(self._backend.list_refs(name)))
        self._pending.move_ref(name, object_hash)

    def list_refs(self, prefix: str) -> list[tuple[str, str]]:
        merged = dict(self._backend.list_refs(prefix))
        merged.update(self._pending.list_refs(prefix))
        return sorted(merged.items())

    def commit(self) -> None:
        """Hand every pending object and ref to the backend, objects first."""
        objects, refs = self._pending.snapshot()
        for object_hash, data in objects.items():
            self._backend.put(object_hash, data)
        for name, object_hash in refs.items():
            self._backend.move_ref(name, object_hash)
        self._pending = InMemoryStore()


class FileStore:
    """Directory-backed store: objects/<hash> files plus refs.json.

    CLE need: the lifecycle spans CLI invocations and days - evidence
    accumulates against artifacts that must outlive a process. Same
    Protocol as InMemoryStore; tests use tmp_path, never a server.
    (P2 decision, documented: this is the persistence the CLI runs on.)
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
        # Checked before the address becomes a path component: see
        # `assert_object_address`.
        assert_object_address(object_hash)
        if content_hash(data) != object_hash:
            raise ValueError(f"content does not hash to requested address {object_hash[:8]}")
        (self._objects_dir / object_hash).write_bytes(data)

    def get(self, object_hash: str) -> bytes:
        assert_object_address(object_hash)
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
    """SQLite-backed store - determinism beyond InMemory, one inspectable file.

    CLE need: the lifecycle persists across processes and must be
    INSPECTABLE - one file you can open with any sqlite client, instead of a
    tree of hash-named blobs. stdlib sqlite3, zero network, deterministic, so
    it is eligible for the default test suite. Same Protocol, same shared
    ref rule as the other backends.

    Selected at runtime via `open_store` (CLE_STORE=sqlite / `--store sqlite`);
    `FileStore` stays the default. Single-writer by design: one commit per
    operation, no WAL and no busy-timeout, so concurrent writers are out of
    scope (the CLI writes, the dashboard reads).
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self._path))
        self._db.execute("CREATE TABLE IF NOT EXISTS objects (hash TEXT PRIMARY KEY, data BLOB)")
        self._db.execute("CREATE TABLE IF NOT EXISTS refs (name TEXT PRIMARY KEY, target TEXT)")
        self._db.commit()

    def put(self, object_hash: str, data: bytes) -> None:
        assert_object_address(object_hash)
        if content_hash(data) != object_hash:
            raise ValueError(f"content does not hash to requested address {object_hash[:8]}")
        self._db.execute(
            "INSERT OR REPLACE INTO objects (hash, data) VALUES (?, ?)", (object_hash, data)
        )
        self._db.commit()

    def get(self, object_hash: str) -> bytes:
        assert_object_address(object_hash)
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


# ── backend selection ────────────────────────────────────────────────────────
# ONE factory, used by every entry point (CLI and dashboard). They must never
# construct a backend independently: a CLI writing sqlite while the dashboard
# reads a FileStore would diverge silently, and the divergence would look like
# data loss rather than a config mistake.
STORE_KINDS = ("file", "sqlite")


def open_store(state_dir: Path | str, kind: str | None = None) -> StoreBackend:
    """Open the persistent store for a state directory.

    `kind` defaults to $CLE_STORE, itself defaulting to "file" - so existing
    state and existing invocations keep working untouched. The two backends
    hold DIFFERENT paths under the same state dir (`store/` vs `store.db`), so
    switching does not read the other's data: it starts an empty one, which is
    honest rather than a silent partial read.
    """
    kind, path = _store_location(state_dir, kind)
    return FileStore(path) if kind == "file" else SqliteStore(path)


def store_exists(state_dir: Path | str, kind: str | None = None) -> bool:
    """Whether `open_store` would find a store here, asked without creating one.

    Opening is not read-only: both backends create their path on construction.
    A caller that must never write into what it reads - `cle population` over
    other users' instances - asks this first.
    """
    return _store_location(state_dir, kind)[1].exists()


def _store_location(state_dir: Path | str, kind: str | None) -> tuple[str, Path]:
    """The backend kind and its path under `state_dir`: one resolution for both."""
    state_dir = Path(state_dir)
    kind = (kind or os.getenv("CLE_STORE") or "file").lower()
    if kind == "file":
        return kind, state_dir / "store"
    if kind == "sqlite":
        return kind, state_dir / "store.db"
    raise ValueError(f"unknown store kind {kind!r}; expected one of {STORE_KINDS}")
