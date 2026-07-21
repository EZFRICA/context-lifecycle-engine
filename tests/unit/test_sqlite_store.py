"""SqliteStore: Protocol conformance parametrized across ALL backends,
plus persistence, integrity, and determinism specific to SQLite.

The conformance block runs the same assertions against InMemoryStore,
FileStore and SqliteStore — one behaviour, three substrates.
"""

import pytest

from cle.oplog import OpLog
from cle.store.backends import (
    FileStore,
    ImmutableRefError,
    InMemoryStore,
    SqliteStore,
    StoreBackend,
)
from cle.store.objects import Block, IntegrityError, content_hash, fetch_verified

import io


@pytest.fixture(params=["memory", "file", "sqlite"])
def store(request, tmp_path):
    if request.param == "memory":
        return InMemoryStore()
    if request.param == "file":
        return FileStore(tmp_path / "store")
    return SqliteStore(tmp_path / "store.db")


def _seed(store, payload: str, ref: str | None = None) -> Block:
    block = Block(kind="prompt_fragment", payload=payload)
    store.put(block.hash, block.canonical_bytes())
    if ref:
        store.move_ref(ref, block.hash)
    return block


# ── conformance (×3 backends) ────────────────────────────────────────────────


def test_conforms_to_protocol(store) -> None:
    assert isinstance(store, StoreBackend)


def test_put_get_round_trip(store) -> None:
    block = _seed(store, "hello")
    assert store.get(block.hash) == block.canonical_bytes()


def test_put_rejects_mislabeled_content(store) -> None:
    with pytest.raises(ValueError):
        store.put("0" * 64, b"mislabeled")


def test_get_missing_raises_keyerror(store) -> None:
    with pytest.raises(KeyError):
        store.get("f" * 64)


def test_mobile_refs_move_freely(store) -> None:
    a, b = _seed(store, "one"), _seed(store, "two")
    store.move_ref("agents/x/trial", a.hash)
    store.move_ref("agents/x/trial", b.hash)
    assert store.list_refs("agents/x/") == [("agents/x/trial", b.hash)]


def test_version_refs_are_immutable(store) -> None:
    a, b = _seed(store, "one"), _seed(store, "two")
    store.move_ref("agents/x/v1.0.0", a.hash)
    with pytest.raises(ImmutableRefError):
        store.move_ref("agents/x/v1.0.0", b.hash)
    assert store.list_refs("agents/x/") == [("agents/x/v1.0.0", a.hash)]


def test_list_refs_prefix_and_sort(store) -> None:
    block = _seed(store, "x")
    store.move_ref("agents/b/trial", block.hash)
    store.move_ref("agents/a/trial", block.hash)
    store.move_ref("topology/v1", block.hash)
    assert [n for n, _ in store.list_refs("agents/")] == ["agents/a/trial", "agents/b/trial"]


def test_verify_on_read_through_backend(store) -> None:
    block = _seed(store, "payload")
    assert fetch_verified(store, block.hash, OpLog(io.StringIO())) == block.canonical_bytes()


def test_snapshot_reflects_state(store) -> None:
    block = _seed(store, "snap", "blocks/snap")
    objects, refs = store.snapshot()
    assert objects[block.hash] == block.canonical_bytes()
    assert refs["blocks/snap"] == block.hash


# ── SQLite-specific ──────────────────────────────────────────────────────────


def test_sqlite_persists_across_reopen(tmp_path) -> None:
    path = tmp_path / "s.db"
    first = SqliteStore(path)
    block = _seed(first, "durable", "blocks/durable")
    first.close()
    second = SqliteStore(path)
    assert second.get(block.hash) == block.canonical_bytes()
    assert second.list_refs("blocks/") == [("blocks/durable", block.hash)]


def test_sqlite_immutability_survives_reopen(tmp_path) -> None:
    path = tmp_path / "s.db"
    first = SqliteStore(path)
    block = _seed(first, "v")
    first.move_ref("agents/a/v1.0.0", block.hash)
    first.close()
    second = SqliteStore(path)
    with pytest.raises(ImmutableRefError):
        second.move_ref("agents/a/v1.0.0", block.hash)


def test_sqlite_tamper_detected_on_read(tmp_path) -> None:
    path = tmp_path / "s.db"
    store = SqliteStore(path)
    block = _seed(store, "clean")
    # Corrupt the stored bytes directly in the database.
    store._db.execute(
        "UPDATE objects SET data = ? WHERE hash = ?",
        (block.canonical_bytes() + b"tampered", block.hash),
    )
    store._db.commit()
    with pytest.raises(IntegrityError):
        fetch_verified(store, block.hash, OpLog(io.StringIO()))


def test_sqlite_snapshot_is_deterministic(tmp_path) -> None:
    store = SqliteStore(tmp_path / "s.db")
    for i in range(5):
        _seed(store, f"payload {i}", f"blocks/b{i}")
    assert store.snapshot() == store.snapshot()


def test_sqlite_binary_payload_round_trip(tmp_path) -> None:
    store = SqliteStore(tmp_path / "s.db")
    data = bytes(range(256)) * 64  # 16 KiB of every byte value
    h = content_hash(data)
    store.put(h, data)
    assert store.get(h) == data
