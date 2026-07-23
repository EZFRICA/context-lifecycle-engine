"""Embedder offline-safety + provenance (adjustment 4 + R3).

The suite must run offline and deterministically: the default embedder is the
CachedEmbedder over committed vectors, a cache miss is an error (never a silent
recompute), and NO test module imports RealEmbedder (the network+key path).
This is a TEST, not a convention — an untested rule drifts on the first rushed
session.
"""

from pathlib import Path

import pytest

from cle.detect.embedders import (
    CachedEmbedder,
    CacheMissError,
    GEMINI_EMBEDDER_ID,
    StubEmbedder,
    cache_key,
    default_embedder,
)

TESTS_DIR = Path(__file__).resolve().parent.parent


def test_default_embedder_is_cached_and_offline() -> None:
    emb = default_embedder()
    assert isinstance(emb, CachedEmbedder)
    assert emb.embedder_id == GEMINI_EMBEDDER_ID


def test_cache_miss_is_an_error_never_a_recompute() -> None:
    emb = CachedEmbedder({}, GEMINI_EMBEDDER_ID)
    with pytest.raises(CacheMissError):
        emb.embed("a text that is not in the committed cache")


def test_cache_key_is_provenance_scoped() -> None:
    # Same text, different embedder id -> different key (different space).
    assert cache_key("google:gemini-embedding-2:768", "hi") != cache_key("stub:hashed64", "hi")


def test_no_test_module_imports_real_embedder() -> None:
    # CI never touches the network or a key: the live embedder is
    # generation-only. Checks actual IMPORT statements (this guard names the
    # class in prose, so a bare substring scan would match itself).
    offenders = []
    for path in TESTS_DIR.rglob("test_*.py"):
        if path.resolve() == Path(__file__).resolve():
            continue
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")) and "RealEmbedder" in stripped:
                offenders.append(f"{path.name}: {stripped}")
    assert offenders == [], f"test modules must not import the live embedder: {offenders}"


def test_stub_embedder_carries_its_id() -> None:
    assert StubEmbedder().embedder_id == "stub:hashed64"
