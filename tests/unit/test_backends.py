"""Backend Protocol conformance and ref rules (cle-core-contracts Store)."""

import pytest

from cle.store.backends import ImmutableRefError, InMemoryStore, StoreBackend
from cle.store.objects import content_hash


def _put(store: InMemoryStore, payload: bytes) -> str:
    stored_hash = content_hash(payload)
    store.put(stored_hash, payload)
    return stored_hash


def test_inmemory_conforms_to_protocol() -> None:
    assert isinstance(InMemoryStore(), StoreBackend)


def test_put_rejects_mislabeled_content() -> None:
    # The store never willingly holds data under a wrong address; corrupt
    # writes are caught at the door, not at read time.
    with pytest.raises(ValueError):
        InMemoryStore().put("0" * 64, b"whatever")


def test_get_round_trips() -> None:
    store = InMemoryStore()
    stored_hash = _put(store, b'{"cle_kind":"block"}')
    assert store.get(stored_hash) == b'{"cle_kind":"block"}'


def test_mobile_state_refs_move_freely() -> None:
    store = InMemoryStore()
    first = _put(store, b'{"n":1}')
    second = _put(store, b'{"n":2}')
    store.move_ref("agents/recap/trial", first)
    store.move_ref("agents/recap/trial", second)  # mobile: re-pointing is the point
    assert store.list_refs("agents/recap/") == [("agents/recap/trial", second)]


def test_version_refs_are_immutable() -> None:
    store = InMemoryStore()
    first = _put(store, b'{"n":1}')
    second = _put(store, b'{"n":2}')
    store.move_ref("agents/recap/v1.0.0", first)  # creation is allowed once
    with pytest.raises(ImmutableRefError):
        store.move_ref("agents/recap/v1.0.0", second)
    # The original pointer survived the attempt.
    assert store.list_refs("agents/recap/") == [("agents/recap/v1.0.0", first)]


def test_list_refs_filters_by_prefix_and_sorts() -> None:
    store = InMemoryStore()
    stored = _put(store, b'{"n":1}')
    store.move_ref("agents/b/trial", stored)
    store.move_ref("agents/a/trial", stored)
    store.move_ref("topology/1", stored)
    assert store.list_refs("agents/") == [
        ("agents/a/trial", stored),
        ("agents/b/trial", stored),
    ]
