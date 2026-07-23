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


# ── R3: centroid provenance is part of agent identity ───────────────────────

import io  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

from cle.build import build_image  # noqa: E402
from cle.build.replay import replay_validate  # noqa: E402
from cle.detect.episodes import DetectorConfig, Message  # noqa: E402
from cle.oplog import OpLog  # noqa: E402
from cle.store.backends import InMemoryStore  # noqa: E402
from cle.store.commits import SourceSpec, SpaceMismatchError, TriggerSpec  # noqa: E402
from cle.store.objects import Block, content_hash  # noqa: E402

T0 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
EMB = StubEmbedder()


class _StubFingerprinter:
    model_id = "stub-model-1"

    def outputs(self, probes):
        return tuple(content_hash({"model": self.model_id, "probe": p}) for p in probes)


def _history() -> list[Message]:
    msgs = []
    for week in range(6):
        start = T0 + timedelta(days=7 * week)
        msgs.append(Message(user_id="u1", ts=start,
                            text="write the weekly recap of my project", thread_id=f"r{week}"))
        msgs.append(Message(user_id="u1", ts=start + timedelta(days=2),
                            text="debug the ingress timeout", thread_id=f"n{week}"))
    return msgs


def _image_built_in_space(embedder_id: str):
    store = InMemoryStore()
    block = Block(kind="prompt_fragment", payload="recap format")
    store.put(block.hash, block.canonical_bytes())
    store.move_ref("blocks/recap_format", block.hash)
    centroid = EMB.embed("write the weekly recap of my project")
    yaml_raw = (
        "name: weekly_recap\n"
        "components:\n"
        "  - '#blocks/recap_format'\n"
        "trigger:\n"
        "  centroid: [" + ", ".join(str(v) for v in centroid) + "]\n"
        f"  embedder_id: {embedder_id}\n"
    )
    return build_image(
        source=SourceSpec(yaml_raw=yaml_raw), backend=store, messages=_history(),
        window_label="30d", existing_triggers=[], embedder=EMB,
        fingerprinter=_StubFingerprinter(), config=DetectorConfig(),
        oplog=OpLog(io.StringIO()), actor="human:test",
    )


def test_embedder_swap_changes_the_image_hash() -> None:
    # Same components, same centroid VALUES, different vector space => a
    # different agent identity. Image.hash covers the trigger, so the hashes
    # must diverge: an embedder swap invalidates centroids exactly as a model
    # swap invalidates fingerprints.
    a = _image_built_in_space("stub:hashed64")
    b = _image_built_in_space("google:gemini-embedding-2:768")
    assert a.trigger.embedder_id != b.trigger.embedder_id
    assert a.hash != b.hash


def test_cross_space_centroid_comparison_raises() -> None:
    a = TriggerSpec(centroid=EMB.embed("x"), embedder_id="stub:hashed64")
    b = TriggerSpec(centroid=EMB.embed("x"), embedder_id="google:gemini-embedding-2:768")
    a.require_same_space(a)  # same space is fine
    with pytest.raises(SpaceMismatchError):
        a.require_same_space(b)


def test_replay_refuses_a_cross_space_incumbent() -> None:
    # The production comparison: routing pits the candidate against incumbents.
    candidate = TriggerSpec(centroid=EMB.embed("write the weekly recap of my project"),
                            embedder_id="stub:hashed64")
    incumbent = TriggerSpec(centroid=EMB.embed("write the weekly recap of my project"),
                            embedder_id="google:gemini-embedding-2:768")
    with pytest.raises(SpaceMismatchError):
        replay_validate(
            trigger=candidate, messages=_history(), window_label="30d",
            existing_triggers=[incumbent], embedder=EMB, config=DetectorConfig(),
            oplog=OpLog(io.StringIO()), actor="human:test",
        )
