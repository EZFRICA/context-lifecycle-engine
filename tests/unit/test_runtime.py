"""P2 runtime: FileStore conformance, mounts, one-way metrics, switch cost."""

import io
import json

import pytest

from cle.oplog import OpLog
from cle.runtime.container import ensure_container, run_prompts, switch_cost
from cle.runtime.metrics_volume import MetricsVolume, read_events
from cle.runtime.mounts import Mount, MountError, validate_mounts
from cle.store.backends import FileStore, ImmutableRefError, StoreBackend
from cle.store.objects import Block, content_hash


def _oplog() -> tuple[OpLog, io.StringIO]:
    sink = io.StringIO()
    return OpLog(sink), sink


def _seed_block(store, payload: str, ref: str | None = None) -> Block:
    block = Block(kind="prompt_fragment", payload=payload)
    store.put(block.hash, block.canonical_bytes())
    if ref:
        store.move_ref(ref, block.hash)
    return block


def _build_image(store, tmp_path, payload: str = "recap format"):
    # Build a real image through the pipeline so runtime tests run on the
    # artifact the store actually holds.
    from datetime import datetime, timedelta, timezone

    from cle.build import build_image
    from cle.detect.clusters import HashedTokenEmbedder
    from cle.detect.episodes import DetectorConfig, Message
    from cle.store.commits import SourceSpec

    embedder = HashedTokenEmbedder()
    _seed_block(store, payload, "blocks/recap_format")
    t0 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    messages = []
    for week in range(5):
        messages.append(
            Message(user_id="u1", ts=t0 + timedelta(days=7 * week), text="write the weekly recap of my project", thread_id=f"r{week}")
        )
        messages.append(
            Message(user_id="u1", ts=t0 + timedelta(days=7 * week + 2), text="debug the ingress timeout", thread_id=f"n{week}")
        )
    centroid = embedder.embed("write the weekly recap of my project")
    yaml_raw = (
        "name: weekly_recap\ncomponents:\n  - '#blocks/recap_format'\n"
        "trigger:\n  centroid: [" + ", ".join(str(v) for v in centroid) + "]\n"
    )

    class Fingerprinter:
        def fingerprint(self, probes):
            return content_hash({"model": "stub", "probes": list(probes)})

    return build_image(
        source=SourceSpec(yaml_raw=yaml_raw),
        backend=store,
        messages=messages,
        window_label="30d",
        existing_triggers=[],
        embedder=embedder,
        fingerprinter=Fingerprinter(),
        config=DetectorConfig(),
        oplog=OpLog(io.StringIO()),
        actor="human:test",
    )


# --- FileStore -------------------------------------------------------------


def test_filestore_conforms_and_persists(tmp_path) -> None:
    store = FileStore(tmp_path / "store")
    assert isinstance(store, StoreBackend)
    block = _seed_block(store, "hello", "blocks/hello")
    reopened = FileStore(tmp_path / "store")
    assert reopened.get(block.hash) == block.canonical_bytes()
    assert reopened.list_refs("blocks/") == [("blocks/hello", block.hash)]


def test_filestore_enforces_ref_and_address_rules(tmp_path) -> None:
    store = FileStore(tmp_path / "store")
    block = _seed_block(store, "x")
    with pytest.raises(ValueError):
        store.put("0" * 64, b"mislabeled")
    store.move_ref("agents/a/v1.0.0", block.hash)
    with pytest.raises(ImmutableRefError):
        store.move_ref("agents/a/v1.0.0", block.hash)
    with pytest.raises(KeyError):
        store.get("f" * 64)


# --- mounts ----------------------------------------------------------------


def test_mount_validation(tmp_path) -> None:
    store = FileStore(tmp_path / "store")
    block = _seed_block(store, "notes", "blocks/notes")
    validate_mounts([Mount(scope_ref="blocks/notes", mode="rw")], store)
    validate_mounts([Mount(scope_ref=block.hash, mode="ro")], store)
    validate_mounts([Mount(scope_ref="mcp://github/issues", mode="ro")], store)

    with pytest.raises(MountError):  # missing ref
        validate_mounts([Mount(scope_ref="blocks/gone", mode="ro")], store)
    with pytest.raises(MountError):  # rw on a content address
        validate_mounts([Mount(scope_ref=block.hash, mode="rw")], store)
    store.move_ref("agents/a/v1.0.0", block.hash)
    with pytest.raises(MountError):  # rw on an immutable version ref
        validate_mounts([Mount(scope_ref="agents/a/v1.0.0", mode="rw")], store)


# --- metrics volume --------------------------------------------------------


def test_metrics_volume_is_write_only_and_readable_from_the_other_side(tmp_path) -> None:
    volume = MetricsVolume(tmp_path, "vol-a")
    volume.record("ws:img1", {"kind": "solicitation"})
    volume.record("ws:img2", {"kind": "solicitation"})
    # The volume object exposes no read surface at all.
    assert not [n for n in dir(volume) if not n.startswith("_") and "read" in n.lower()]
    events = read_events(tmp_path, "vol-a")
    assert len(events) == 2
    assert read_events(tmp_path, "vol-a", "ws:img1")[0]["container_id"] == "ws:img1"
    assert all("ts" in event for event in events)


# --- container runtime -----------------------------------------------------


def test_ensure_run_and_switch_with_costs(tmp_path) -> None:
    store = FileStore(tmp_path / "store")
    state_root = tmp_path / "state"
    oplog, sink = _oplog()

    image_a = _build_image(store, tmp_path, "recap format v1")
    container = ensure_container(
        state_root=state_root,
        backend=store,
        image_hash=image_a.hash,
        workspace_id="alpha",
        mounts=[Mount(scope_ref="blocks/recap_format", mode="ro")],
        oplog=oplog,
        actor="human:test",
    )
    run_prompts(
        state_root=state_root,
        backend=store,
        container=container,
        prompts=["write the recap", "make it shorter please"],
        oplog=oplog,
        actor="human:test",
    )
    events = read_events(state_root, container.metrics_volume_id)
    kinds = [event["kind"] for event in events]
    assert kinds.count("solicitation") == 2 and kinds.count("closure") == 2

    # Second image differs by one block: switch must log both costs.
    _seed_block(store, "recap format v2 with extra sections", "blocks/recap_format")
    image_b = _build_image(store, tmp_path, "recap format v2 with extra sections")
    assert image_b.hash != image_a.hash
    ensure_container(
        state_root=state_root,
        backend=store,
        image_hash=image_b.hash,
        workspace_id="alpha",
        mounts=[Mount(scope_ref="blocks/recap_format", mode="ro")],
        oplog=oplog,
        actor="human:test",
    )
    switches = [
        json.loads(line) for line in sink.getvalue().splitlines() if '"op": "switch"' in line
    ]
    assert len(switches) == 1
    record = switches[0]
    expected_blocks, expected_tokens = switch_cost(store, image_a, image_b, oplog)
    assert record["diff_blocks"] == expected_blocks == 2  # one block out, one in
    assert record["diff_tokens"] == expected_tokens > 0
    assert record["from"] == image_a.hash[:8] and record["image"] == image_b.hash[:8]


def test_solicit_writes_no_store_objects(tmp_path) -> None:
    store = FileStore(tmp_path / "store")
    state_root = tmp_path / "state"
    oplog, _ = _oplog()
    image = _build_image(store, tmp_path)
    container = ensure_container(
        state_root=state_root,
        backend=store,
        image_hash=image.hash,
        workspace_id="beta",
        mounts=[],
        oplog=oplog,
        actor="human:test",
    )
    before = store.snapshot()
    run_prompts(
        state_root=state_root,
        backend=store,
        container=container,
        prompts=["hello"],
        oplog=oplog,
        actor="human:test",
    )
    assert store.snapshot() == before
