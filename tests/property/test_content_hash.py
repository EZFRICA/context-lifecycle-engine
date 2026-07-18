"""Canonical hashing properties — the foundation of both hash namespaces.

content_hash is THE hashing function (cle-core-contracts): canonical JSON,
sorted keys, no whitespace, UTF-8, sha256. Written before objects.py per
the TDD-on-invariants rule.
"""

import hashlib
import json

from hypothesis import given
from hypothesis import strategies as st

from cle.store.objects import Block, content_hash

# JSON-shaped values: scalars, and nested lists/dicts of scalars.
json_scalars = st.none() | st.booleans() | st.integers() | st.text()
json_values = st.recursive(
    json_scalars,
    lambda children: st.lists(children, max_size=4)
    | st.dictionaries(st.text(max_size=8), children, max_size=4),
    max_leaves=10,
)


@given(json_values)
def test_hash_is_deterministic(value) -> None:
    assert content_hash(value) == content_hash(value)


@given(json_values)
def test_object_hash_matches_independent_canonical_encoding(value) -> None:
    # Pins all three canonicalization clauses at once (sorted keys, no
    # whitespace, UTF-8) against an encoding built independently of the
    # implementation — the other properties are corollaries of this one.
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    assert content_hash(value) == hashlib.sha256(canonical).hexdigest()


@given(st.dictionaries(st.text(min_size=1, max_size=8), json_scalars, min_size=2, max_size=6))
def test_hash_ignores_key_insertion_order(mapping) -> None:
    # Same mapping built in reverse insertion order must hash identically —
    # canonicalization, not memory layout, defines identity.
    reversed_insertion = dict(reversed(list(mapping.items())))
    assert content_hash(mapping) == content_hash(reversed_insertion)


@given(st.text())
def test_bytes_are_hashed_as_stored(payload: str) -> None:
    # Backends hand back raw canonical bytes; hashing them must reproduce
    # the address they were stored under without re-canonicalizing.
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    assert content_hash(data) == hashlib.sha256(data).hexdigest()


@given(st.text(max_size=32), st.text(max_size=32))
def test_distinct_payloads_hash_differently(a: str, b: str) -> None:
    if a != b:
        assert content_hash({"payload": a}) != content_hash({"payload": b})


@given(kind=st.text(min_size=1, max_size=8), payload=st.text(max_size=64))
def test_block_hash_matches_its_canonical_bytes(kind: str, payload: str) -> None:
    # A Block's address and its stored encoding must agree, or verify-on-
    # read would reject every legitimate fetch.
    block = Block(kind=kind, payload=payload)
    assert block.hash == content_hash(block.canonical_bytes())
