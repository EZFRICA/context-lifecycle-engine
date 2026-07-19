"""`cle` command-line interface — build | run | ps | tag | log | diff
(BLUEPRINT §1 CLI surface) plus revalidate (BLUEPRINT §5 / P3: the
re-validator needs a human-invocable entry point until v2 schedules it).

State model (decision, documented): the CLI persists on a FileStore under
--state-dir (default .cle/) — store objects+refs, containers.json,
metrics/, log.jsonl — because the lifecycle outlives any process. The
visible topology.yaml is written next to the state dir root.
"""

import getpass
import json
import re
import os
import sys
from datetime import timedelta
from pathlib import Path

import typer
import yaml

from cle.build import build_image
from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.episodes import DetectorConfig, Message
from cle.lifecycle.engine import EngineThresholds, shadow_decide
from cle.lifecycle.revalidator import revalidate as run_revalidation
from cle.lifecycle.tags import move_state_tag
from cle.lifecycle.topology import current_agents, render_diff, render_log, write_topology
from cle.oplog import OpLog
from cle.runtime.container import ensure_container, load_containers, load_image, run_prompts
from cle.runtime.metrics_volume import read_events
from cle.runtime.mounts import Mount
from cle.store.backends import FileStore
from cle.store.commits import Evidence, SourceSpec
from cle.store.objects import Block, content_hash

app = typer.Typer(help="CLE — Context Lifecycle Engine.")

_WINDOW = re.compile(r"^(\d+)([dh])$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
STATE_DIR_OPTION = typer.Option(Path(".cle"), "--state-dir", help="Persistent CLE state.")


@app.callback()
def cli() -> None:
    """The lifecycle CLI: evidence in, tags moved, everything logged."""


class StubFingerprinter:
    """Deterministic substrate stand-in (no live model in v1): per-probe
    output = hash(model_id, probe). Drift is simulated by changing
    --model-id — same Protocol a live provider implements."""

    def __init__(self, model_id: str = "stub-model-1") -> None:
        self.model_id = model_id

    def outputs(self, probes) -> tuple[str, ...]:
        return tuple(content_hash({"model": self.model_id, "probe": p}) for p in probes)


def _parse_window(label: str) -> timedelta:
    match = _WINDOW.match(label)
    if not match:
        raise typer.BadParameter(f"window must look like 30d or 48h, got {label!r}")
    value, unit = int(match.group(1)), match.group(2)
    return timedelta(days=value) if unit == "d" else timedelta(hours=value)


def _store(state_dir: Path) -> FileStore:
    return FileStore(state_dir / "store")


def _oplog(state_dir: Path):
    state_dir.mkdir(parents=True, exist_ok=True)
    sink = (state_dir / "log.jsonl").open("a")
    return OpLog(sink), sink


def _actor() -> str:
    # CLE_ACTOR overrides; otherwise the OS user — never a hardcoded name.
    return f"human:{os.getenv('CLE_ACTOR') or getpass.getuser()}"


def _resolve_image_hash(backend: FileStore, agent_or_image: str) -> tuple[str, str | None]:
    """Accept a raw image hash or an agent name from the topology."""
    if _HASH.match(agent_or_image):
        return agent_or_image, None
    agents = current_agents(backend)
    if agent_or_image not in agents:
        typer.echo(f"unknown agent {agent_or_image!r}; topology has {sorted(agents)}", err=True)
        raise typer.Exit(code=1)
    return agents[agent_or_image]["image"], agent_or_image


def _load_history(path: Path) -> list[Message]:
    messages = [
        Message.model_validate(json.loads(line))
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    return sorted(messages, key=lambda m: m.ts)


def _seed_components(store: FileStore, components_dir: Path) -> None:
    # Simulates the populated store a running CLE would have.
    for component_file in sorted(components_dir.glob("*.yaml")):
        spec = yaml.safe_load(component_file.read_text())
        block = Block(kind=spec["kind"], payload=spec["payload"])
        store.put(block.hash, block.canonical_bytes())
        store.move_ref(spec["ref"], block.hash)


@app.command()
def build(
    source_path: Path = typer.Argument(..., help="Candidate source YAML (detector-written)."),
    replay_window: str = typer.Option("30d", help="Replay window, e.g. 30d or 48h."),
    history: Path = typer.Option(Path("examples/prompt_history.jsonl")),
    components: Path = typer.Option(Path("examples/components")),
    model_id: str = typer.Option(
        "current",
        help="Substrate for the fingerprint: 'current' = configured live model; "
        "a real model name = build on THAT model; 'stub-*' = deterministic offline.",
    ),
    state_dir: Path = STATE_DIR_OPTION,
) -> None:
    """Three-stage build; on success the candidate is born (tag + topology)."""
    source = SourceSpec(yaml_raw=source_path.read_text())
    agent_name = yaml.safe_load(source.yaml_raw).get("name", "unnamed")
    all_messages = _load_history(history)
    if not all_messages:
        typer.echo("history is empty; nothing to replay", err=True)
        raise typer.Exit(code=1)
    # Deterministic window anchor: the end of recorded history.
    window_end = all_messages[-1].ts
    window_messages = [m for m in all_messages if m.ts >= window_end - _parse_window(replay_window)]

    from cle.build.fingerprinter import LiveModelFingerprinter
    store = _store(state_dir)
    _seed_components(store, components)
    oplog, sink = _oplog(state_dir)
    try:
        if model_id.startswith("stub-") or model_id.startswith("drifted-"):
            fingerprinter = StubFingerprinter(model_id)  # deterministic, offline
        elif model_id in ("current", "live"):
            fingerprinter = LiveModelFingerprinter()  # configured model, temp 0
        else:
            fingerprinter = LiveModelFingerprinter(model_override=model_id)  # named real model
        # Replay against the topology AUGMENTED with the candidate (BLUEPRINT
        # §3.2): existing agents' triggers compete, so capture_rate reflects
        # what this candidate would ACTUALLY intercept, not what it could in a
        # vacuum. A rebuild of the same agent excludes its own prior trigger.
        existing_triggers = []
        for other, entry in current_agents(store).items():
            if other == agent_name:
                continue
            try:
                existing_triggers.append(load_image(store, entry["image"], oplog).trigger)
            except Exception:
                pass
        image = build_image(
            source=source, backend=store, messages=window_messages,
            window_label=replay_window, existing_triggers=existing_triggers,
            embedder=HashedTokenEmbedder(), fingerprinter=fingerprinter,
            config=DetectorConfig(), oplog=oplog, actor=_actor(),
        )
        # Birth: the candidate tag and its topology entry, both carrying
        # the replay's pre_evidence (never more than that at birth).
        move_state_tag(
            backend=store, agent=agent_name, image_hash=image.hash, from_state=None,
            to_state="candidate", pre_evidence=image.pre_evidence, oplog=oplog, actor=_actor(),
        )
        write_topology(
            backend=store, path=state_dir / "topology.yaml", agent=agent_name,
            state="candidate", image_hash=image.hash,
            cause={"pre_evidence": image.pre_evidence.model_dump()}, oplog=oplog, actor=_actor(),
        )
    except Exception as error:
        typer.echo(f"build failed: {error}", err=True)
        raise typer.Exit(code=1)
    finally:
        sink.close()

    report = image.pre_evidence
    typer.echo(f"capture_rate        {report.capture_rate:.3f}")
    typer.echo(f"false_trigger_rate  {report.false_trigger_rate:.3f}")
    typer.echo(f"historical_cost     {report.historical_cost:.2f} iterations/episode")
    typer.echo(f"window              {report.window}  ({len(window_messages)} messages)")
    typer.echo(f"source_hash         {image.source_hash}")
    typer.echo(f"image_hash          {image.hash}")
    typer.echo(f"two_hashes_distinct {image.hash != image.source_hash}")
    typer.echo(f"agent               {agent_name} -> candidate")


@app.command()
def run(
    agent_or_image: str = typer.Argument(..., help="Agent name (topology) or image hash."),
    workspace: str = typer.Option(..., "--workspace"),
    prompts: int = typer.Option(3, "--prompts", help="Simulated solicitations."),
    state_dir: Path = STATE_DIR_OPTION,
) -> None:
    """Instantiate (or switch) the workspace's container and solicit it."""
    store = _store(state_dir)
    image_hash, _ = _resolve_image_hash(store, agent_or_image)
    oplog, sink = _oplog(state_dir)
    try:
        image = load_image(store, image_hash, oplog)
        # Mount policy (decision): the image's own components, read-only —
        # scopes come from what the image was built with, nothing more.
        mounts = [Mount(scope_ref=ref, mode="ro") for ref in image.resolved_refs.values()]
        container = ensure_container(
            state_root=state_dir, backend=store, image_hash=image_hash,
            workspace_id=workspace, mounts=mounts, oplog=oplog, actor=_actor(),
        )
        # Workspace-flavored prompts so metrics genuinely diverge.
        texts = [f"{workspace} request {i} for the {workspace} team" * (1 + i % 2) for i in range(prompts)]
        for response in run_prompts(
            state_root=state_dir, backend=store, container=container,
            prompts=texts, oplog=oplog, actor=_actor(),
        ):
            typer.echo(response)
    finally:
        sink.close()


@app.command()
def ps(state_dir: Path = STATE_DIR_OPTION) -> None:
    """Containers and their per-container metrics (read from the system
    volume — the human side of the Goodhart boundary)."""
    containers = load_containers(state_dir)
    if not containers:
        typer.echo("(no containers)")
        return
    for workspace, container in sorted(containers.items()):
        events = read_events(state_dir, container.metrics_volume_id)
        solicitations = sum(1 for e in events if e["kind"] == "solicitation")
        iterations = sum(e.get("count", 0) for e in events if e["kind"] == "iterations")
        closures: dict[str, int] = {}
        for event in events:
            if event["kind"] == "closure":
                closures[event["tag"]] = closures.get(event["tag"], 0) + 1
        typer.echo(
            f"{workspace:<10} image={container.image_hash[:8]} "
            f"solicitations={solicitations} iterations={iterations} closures={closures}"
        )


@app.command()
def tag(
    agent: str = typer.Argument(...),
    to_state: str = typer.Argument(...),
    cost_ratio: float | None = typer.Option(None),
    occurrences: int | None = typer.Option(None),
    closures: str | None = typer.Option(None, help="Comma-separated closure tags."),
    reason: str | None = typer.Option(None),
    state_dir: Path = STATE_DIR_OPTION,
) -> None:
    """Move an agent's state tag (humans only; the engine shadows you)."""
    store = _store(state_dir)
    agents = current_agents(store)
    entry = agents.get(agent)
    if entry is None:
        typer.echo(f"unknown agent {agent!r}", err=True)
        raise typer.Exit(code=1)
    from_state, image_hash = entry["state"], entry["image"]

    evidence = None
    if cost_ratio is not None and occurrences is not None:
        evidence = Evidence(
            cost_ratio=cost_ratio, occurrences=occurrences,
            closure_tags=tuple((closures or "").split(",")) if closures else (),
        )
    pre_evidence = None
    oplog, sink = _oplog(state_dir)
    try:
        if evidence is None and to_state in ("trial", "candidate"):
            pre_evidence = load_image(store, image_hash, oplog).pre_evidence
        move_state_tag(
            backend=store, agent=agent, image_hash=image_hash, from_state=from_state,
            to_state=to_state, evidence=evidence, pre_evidence=pre_evidence,
            reason=reason, oplog=oplog, actor=_actor(),
        )
        cause: dict = {}
        if evidence is not None:
            cause["evidence"] = evidence.model_dump()
        elif pre_evidence is not None:
            cause["pre_evidence"] = pre_evidence.model_dump()
        else:  # downward move: accountability, not proof
            cause["reason"] = reason
        write_topology(
            backend=store, path=state_dir / "topology.yaml", agent=agent,
            state=to_state, image_hash=image_hash, cause=cause, oplog=oplog, actor=_actor(),
        )
        # The shadow engine judges the same evidence and logs its own call
        # — the divergence log is the article-9 deliverable.
        if evidence is not None:
            would = shadow_decide(
                state=from_state, evidence=evidence, thresholds=EngineThresholds(),
                image_hash=image_hash, oplog=oplog,
            )
            typer.echo(f"human: {from_state} -> {to_state} | engine:shadow would: {would}")
        else:
            typer.echo(f"human: {from_state} -> {to_state}")
    except Exception as error:
        typer.echo(f"tag failed: {error}", err=True)
        raise typer.Exit(code=1)
    finally:
        sink.close()


@app.command()
def log(
    target: str | None = typer.Argument(None, help="'topology.yaml' for topology history."),
    tail: int = typer.Option(20, "--tail"),
    state_dir: Path = STATE_DIR_OPTION,
) -> None:
    """Op log (default) or topology history with provenance."""
    if target == "topology.yaml":
        typer.echo(render_log(_store(state_dir)))
        return
    log_path = state_dir / "log.jsonl"
    if not log_path.exists():
        typer.echo("(no log)")
        return
    for line in log_path.read_text().splitlines()[-tail:]:
        typer.echo(line)


@app.command()
def dashboard(
    port: int = typer.Option(8000, help="Port to run the dashboard server on."),
    state_dir: Path = STATE_DIR_OPTION,
) -> None:
    """Launch the Web Dashboard and API server."""
    import uvicorn
    import os
    # Expose state_dir via environment variable so dashboard backend knows where to find it
    os.environ["CLE_STATE_DIR"] = str(state_dir.resolve())
    typer.echo(f"Initializing FastAPI dashboard server against state dir: {state_dir}")
    uvicorn.run("dashboard.backend.app:app", host="127.0.0.1", port=port, log_level="info")


@app.command()
def diff(
    version_a: str = typer.Argument(..., help="e.g. topology/v1"),
    version_b: str = typer.Argument(...),
    state_dir: Path = STATE_DIR_OPTION,
) -> None:
    """Learned-topology delta between two versions."""
    typer.echo(render_diff(_store(state_dir), version_a, version_b))


@app.command()
def revalidate(
    agent_or_image: str = typer.Argument(...),
    model_id: str = typer.Option(
        "current",
        help="'current' = configured live model; a real model name = probe THAT model "
        "(real drift); 'stub-*'/'drifted-*' = deterministic simulated drift.",
    ),
    state_dir: Path = STATE_DIR_OPTION,
) -> None:
    """Replay the frozen probe set; drift auto-demotes to trial."""
    store = _store(state_dir)
    image_hash, agent = _resolve_image_hash(store, agent_or_image)
    oplog, sink = _oplog(state_dir)
    try:
        from cle.build.fingerprinter import LiveModelFingerprinter

        if model_id.startswith("drifted-") or model_id.startswith("stub-"):
            # Deterministic simulated drift (offline, reproducible).
            fingerprinter = StubFingerprinter(model_id)
        elif model_id in ("current", "live"):
            # Probe the SAME configured model — proof holds unless it moved.
            fingerprinter = LiveModelFingerprinter()
        else:
            # Probe a DIFFERENT real model to enact a genuine substrate drift.
            fingerprinter = LiveModelFingerprinter(model_override=model_id)

        persistence = run_revalidation(
            backend=store, image_hash=image_hash,
            fingerprinter=fingerprinter, oplog=oplog, actor="engine:revalidator",
        )
        if not persistence.probe_deltas:
            typer.echo("proof holds: fingerprint unchanged")
            return
        probe_total = len(load_image(store, image_hash, oplog).probe_set)
        typer.echo(f"DRIFT: {len(persistence.probe_deltas)}/{probe_total} probes moved")
        if agent is not None:
            entry = current_agents(store)[agent]
            if entry["state"] in ("ephemeral", "pinned"):
                move_state_tag(
                    backend=store, agent=agent, image_hash=image_hash,
                    from_state=entry["state"], to_state="trial",
                    reason=f"fingerprint drift under {model_id}",
                    oplog=oplog, actor="engine:revalidator",
                )
                write_topology(
                    backend=store, path=state_dir / "topology.yaml", agent=agent,
                    state="trial", image_hash=image_hash,
                    cause={"persistence": persistence.model_dump()},
                    oplog=oplog, actor="engine:revalidator",
                )
                typer.echo(f"{agent}: {entry['state']} -> trial (auto-demoted)")
    finally:
        sink.close()


@app.command()
def decline(
    agent: str = typer.Argument(..., help="Candidate agent to refuse."),
    reason: str | None = typer.Option(None, help="Optional human reason (logged)."),
    state_dir: Path = STATE_DIR_OPTION,
) -> None:
    """Refuse a candidate — the human 'Decline' on the proposal menu.

    Writes no tag and moves nothing; it records the refusal as one op line
    so the divergence between what the system proposed and what the human
    accepted is auditable (the article-9 data). This is a write path, so
    like every write it goes through the CLI and is logged.
    """
    store = _store(state_dir)
    agents = current_agents(store)
    entry = agents.get(agent)
    if entry is None:
        typer.echo(f"unknown agent {agent!r}", err=True)
        raise typer.Exit(code=1)
    oplog, sink = _oplog(state_dir)
    try:
        oplog.emit(
            "candidate_declined",
            actor=_actor(),
            image=entry["image"],
            agent=agent,
            from_state=entry["state"],
            **({"reason": reason} if reason else {}),
        )
        typer.echo(f"declined {agent} (was {entry['state']})")
    finally:
        sink.close()


@app.command()
def clean(
    state_dir: Path = STATE_DIR_OPTION,
) -> None:
    """Reset the CLE state directory (deletes all persistent state)."""
    import shutil
    if state_dir.exists():
        shutil.rmtree(state_dir)
        typer.echo(f"CLE state directory {state_dir} has been reset.")
    else:
        typer.echo(f"CLE state directory {state_dir} does not exist.")


if __name__ == "__main__":
    app()
