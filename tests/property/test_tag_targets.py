"""Invariant 1, tag half — lifecycle tags attach to Image hashes only.

Mandated test 2 of cle-core-contracts (test_tag_source_raises), written
before the guard it enforces. The guard inspects the stored record's
cle_kind domain marker, so anything that is not an image — source specs,
blocks, arbitrary records — is rejected at the tagging boundary.
"""

import io
import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cle.oplog import OpLog
from cle.store.backends import InMemoryStore
from cle.store.commits import SourceSpec, TagTargetError, assert_tag_target
from cle.store.objects import Block, content_hash


def _store_canonical(store: InMemoryStore, data: bytes) -> str:
    stored_hash = content_hash(data)
    store.put(stored_hash, data)
    return stored_hash


@given(yaml_raw=st.text(min_size=1, max_size=200))
def test_tag_source_raises(yaml_raw: str) -> None:
    store = InMemoryStore()
    source = SourceSpec(yaml_raw=yaml_raw)
    source_hash = _store_canonical(store, source.canonical_bytes())
    with pytest.raises(TagTargetError):
        assert_tag_target(store, source_hash, OpLog(io.StringIO()))


@given(kind=st.text(min_size=1, max_size=16), payload=st.text(max_size=64))
def test_tag_block_raises(kind: str, payload: str) -> None:
    # Blocks are components, not lifecycle subjects — same rejection.
    store = InMemoryStore()
    block_hash = _store_canonical(store, Block(kind=kind, payload=payload).canonical_bytes())
    with pytest.raises(TagTargetError):
        assert_tag_target(store, block_hash, OpLog(io.StringIO()))


def test_tag_image_record_passes() -> None:
    # A record carrying the image domain marker is a legitimate target.
    # (The full Image model lands in later commits; the guard contract is
    # about the domain marker, which is what this pins.)
    store = InMemoryStore()
    image_record = json.dumps(
        {"cle_kind": "image", "source_hash": "0" * 64}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    image_hash = _store_canonical(store, image_record)
    assert_tag_target(store, image_hash, OpLog(io.StringIO()))  # must not raise


def test_source_and_image_hash_namespaces_are_domain_separated() -> None:
    # Identical inner content under different cle_kind markers yields
    # different addresses — the structural half of the two-hash invariant.
    source = SourceSpec(yaml_raw="name: recap")
    imposter = json.loads(source.canonical_bytes())
    # The marker must actually be stamped — this line fails if Storable
    # ever stops writing cle_kind, keeping the invariant tested rather
    # than merely documented.
    assert imposter.pop("cle_kind") == "source_spec"
    imposter["cle_kind"] = "image"
    assert content_hash(imposter) != source.hash


def test_non_json_record_raises_tag_target_error() -> None:
    # put() validates addresses, not JSON-ness — arbitrary bytes are
    # legitimate store content, and the tagging boundary must reject them
    # with the typed error, never leak a decode error.
    store = InMemoryStore()
    raw = b"not json at all"
    stored_hash = _store_canonical(store, raw)
    with pytest.raises(TagTargetError):
        assert_tag_target(store, stored_hash, OpLog(io.StringIO()))
