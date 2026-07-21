"""Tool kind + two-stage capability gating (build side).

Tools are DECLARATIONS (name + capability tag), never runnable code — no
execution, no API call, no network anywhere in these tests.
"""

import io
import json

import pytest

from cle.build import build_image
from cle.build.resolver import ResolutionError, resolve
from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.episodes import DetectorConfig
from cle.oplog import OpLog
from cle.store.backends import InMemoryStore, SqliteStore
from cle.store.commits import SourceSpec
from cle.store.objects import Block, content_hash

from tests.unit.test_runtime import _build_image  # baseline pipeline helper

EMBEDDER = HashedTokenEmbedder()


def _tool(store, name: str, capability: str) -> Block:
    block = Block(kind="tool", payload=json.dumps({"name": name, "capability": capability}))
    store.put(block.hash, block.canonical_bytes())
    store.move_ref(f"tools/{name}", block.hash)
    return block


def _seed_component(store) -> None:
    block = Block(kind="prompt_fragment", payload="recap format")
    store.put(block.hash, block.canonical_bytes())
    store.move_ref("blocks/recap_format", block.hash)


def _yaml(tools: list[str] | None = None, requires: list[str] | None = None) -> str:
    centroid = EMBEDDER.embed("write the weekly recap of my project")
    lines = ["name: weekly_recap", "components:", "  - '#blocks/recap_format'"]
    if tools is not None:
        lines.append("tools:")
        lines += [f"  - {t}" for t in tools]
    lines.append("trigger:")
    lines.append("  centroid: [" + ", ".join(str(v) for v in centroid) + "]")
    if requires is not None:
        lines.append("  requires_tools:")
        lines += [f"    - {t}" for t in requires]
    return "\n".join(lines) + "\n"


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    s = InMemoryStore() if request.param == "memory" else SqliteStore(tmp_path / "s.db")
    _seed_component(s)
    return s


# ── stage 1: library check ───────────────────────────────────────────────────


def test_declared_tool_resolves_when_in_library(store) -> None:
    _tool(store, "calendar_api", "events")
    resolved = resolve(
        SourceSpec(yaml_raw=_yaml(tools=["calendar_api"])), store, OpLog(io.StringIO()), "human:t"
    )
    assert "#blocks/recap_format" in resolved


def test_missing_library_tool_fails_resolution(store) -> None:
    with pytest.raises(ResolutionError, match="unresolved tool calendar_api"):
        resolve(
            SourceSpec(yaml_raw=_yaml(tools=["calendar_api"])), store, OpLog(io.StringIO()), "human:t"
        )


def test_non_tool_ref_under_tools_namespace_fails(store) -> None:
    # A block masquerading under tools/ is not a capability declaration.
    fake = Block(kind="prompt_fragment", payload="not a tool")
    store.put(fake.hash, fake.canonical_bytes())
    store.move_ref("tools/calendar_api", fake.hash)
    with pytest.raises(ResolutionError, match="not a tool declaration"):
        resolve(
            SourceSpec(yaml_raw=_yaml(tools=["calendar_api"])), store, OpLog(io.StringIO()), "human:t"
        )


def test_missing_tool_failure_writes_nothing_and_logs_stage(store) -> None:
    before = store.snapshot()
    sink = io.StringIO()
    with pytest.raises(ResolutionError):
        resolve(SourceSpec(yaml_raw=_yaml(tools=["ghost_tool"])), store, OpLog(sink), "human:t")
    assert store.snapshot() == before  # staged failure: byte-identical store
    lines = [json.loads(l) for l in sink.getvalue().splitlines()]
    assert [l["op"] for l in lines] == ["build"]
    assert lines[0]["stage"] == "resolve" and lines[0]["outcome"] == "failed"


# ── stage 1: mount coverage ──────────────────────────────────────────────────


def test_trigger_requirement_not_mounted_fails(store) -> None:
    _tool(store, "calendar_api", "events")
    with pytest.raises(ResolutionError, match="tool required by trigger not mounted"):
        resolve(
            SourceSpec(yaml_raw=_yaml(tools=[], requires=["calendar_api"])),
            store, OpLog(io.StringIO()), "human:t",
        )


def test_trigger_requirement_covered_by_mount_passes(store) -> None:
    _tool(store, "calendar_api", "events")
    resolve(
        SourceSpec(yaml_raw=_yaml(tools=["calendar_api"], requires=["calendar_api"])),
        store, OpLog(io.StringIO()), "human:t",
    )


def test_mount_coverage_failure_writes_nothing(store) -> None:
    _tool(store, "calendar_api", "events")
    before = store.snapshot()
    with pytest.raises(ResolutionError):
        resolve(
            SourceSpec(yaml_raw=_yaml(tools=[], requires=["calendar_api"])),
            store, OpLog(io.StringIO()), "human:t",
        )
    assert store.snapshot() == before


def test_malformed_tools_list_fails(store) -> None:
    src = SourceSpec(yaml_raw="name: x\ncomponents:\n  - '#blocks/recap_format'\ntools: notalist\n")
    with pytest.raises(ResolutionError, match="`tools` must be a list"):
        resolve(src, store, OpLog(io.StringIO()), "human:t")


# ── image identity ───────────────────────────────────────────────────────────


def test_mounted_tools_are_hash_covered(tmp_path) -> None:
    store = InMemoryStore()
    image = _build_image(store, tmp_path)
    tampered = image.model_copy(update={"mounted_tools": ("calendar_api",)})
    assert tampered.hash != image.hash  # capability set is part of identity


def test_tool_payload_never_reaches_the_prompt(tmp_path) -> None:
    # Even if a tool ref is (wrongly) listed under components, assembly
    # must not concatenate a capability declaration into prompt text.
    store = InMemoryStore()
    _seed_component(store)
    _tool(store, "calendar_api", "events")
    centroid = EMBEDDER.embed("write the weekly recap of my project")
    yaml_raw = (
        "name: weekly_recap\ncomponents:\n  - '#blocks/recap_format'\n  - '#tools/calendar_api'\n"
        "tools:\n  - calendar_api\n"
        "trigger:\n  centroid: [" + ", ".join(str(v) for v in centroid) + "]\n"
    )
    from tests.unit.test_runtime import _build_image as _bi  # reuse messages/fingerprinter

    # Build via the real pipeline with this custom source.
    from datetime import datetime, timedelta, timezone

    from cle.detect.episodes import Message

    t0 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    messages = []
    for week in range(5):
        messages.append(Message(user_id="u1", ts=t0 + timedelta(days=7 * week),
                                text="write the weekly recap of my project", thread_id=f"r{week}"))
        messages.append(Message(user_id="u1", ts=t0 + timedelta(days=7 * week + 2),
                                text="debug the ingress timeout", thread_id=f"n{week}"))

    class Fp:
        def outputs(self, probes):
            return tuple(content_hash({"m": "stub", "p": p}) for p in probes)

    image = build_image(
        source=SourceSpec(yaml_raw=yaml_raw), backend=store, messages=messages,
        window_label="30d", existing_triggers=[], embedder=EMBEDDER, fingerprinter=Fp(),
        config=DetectorConfig(), oplog=OpLog(io.StringIO()), actor="human:t",
    )
    assert "calendar_api" not in image.assembled_prompt
    assert image.mounted_tools == ("calendar_api",)
