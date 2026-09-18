"""Backend Protocol conformance and ref rules (cle-core-contracts Store)."""

import pytest

from cle.store.backends import (
    FileStore,
    ImmutableRefError,
    InMemoryStore,
    InvalidAddressError,
    SqliteStore,
    StoreBackend,
)
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


#: An address that is not a hash, in the three shapes that reach a store from
#: outside it: a path, a wildcard, and an address of the right length in the
#: wrong alphabet.
NOT_ADDRESSES = ("../../witness.txt", "objects/../../etc/passwd", "*", "", "G" * 64, "0" * 63)


@pytest.mark.parametrize("address", NOT_ADDRESSES)
def test_no_backend_accepts_an_address_that_is_not_a_hash(address, tmp_path) -> None:
    stores = [InMemoryStore(), FileStore(tmp_path / "file"), SqliteStore(tmp_path / "db.sqlite")]
    for store in stores:
        with pytest.raises(InvalidAddressError):
            store.get(address)
        with pytest.raises(InvalidAddressError):
            store.put(address, b"whatever")


def test_a_traversing_address_reads_nothing_outside_the_store(tmp_path) -> None:
    """The measured defect: `FileStore` turned an address into a path, so an
    address of `../../witness.txt` returned that file's bytes and the refusal
    for a normal miss (`KeyError`) made it look like nothing had happened."""
    witness = tmp_path / "witness.txt"
    witness.write_text("a secret file")
    store = FileStore(tmp_path / "state" / "store")

    with pytest.raises(InvalidAddressError) as refusal:
        store.get("../../witness.txt")

    assert "a secret file" not in str(refusal.value)
    assert witness.read_text() == "a secret file"     # and put wrote nothing over it
    with pytest.raises(InvalidAddressError):
        store.put("../../witness.txt", b"overwritten")
    assert witness.read_text() == "a secret file"


def test_an_invalid_address_is_a_value_error_like_a_mislabeled_one() -> None:
    """Callers catching `ValueError` around a `put` keep catching both refusals."""
    with pytest.raises(ValueError):
        InMemoryStore().get("not-a-hash")


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
