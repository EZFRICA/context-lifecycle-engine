"""`cle` command-line interface.

BLUEPRINT §1 surface — build | run | ps | tag | log | diff — plus four
commands the build needed and the contract did not name:
- `revalidate` (BLUEPRINT §5 / P3: the re-validator needs a human-invocable
  entry point until v2 schedules it),
- `decline` (records a human refusal as one op line, moving no tag — the
  human/engine divergence must be auditable in both directions),
- `dashboard` (serves the FastAPI read-mostly view),
- `clean` (resets the state directory).
Every command emits exactly one JSON op line per operation (invariant 4);
upward tag moves carry `evidence`.

State model (decision, documented): the CLI persists on a store selected by
`--store` / $CLE_STORE (FileStore by default, SqliteStore opt-in) under
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
from cle.detect.embedders import EMBEDDER_KINDS, open_embedder, embedding_config_for
from cle.detect.episodes import DetectorConfig, Message
from cle.lifecycle.engine import EngineThresholds, shadow_decide
from cle.lifecycle.revalidator import revalidate as run_revalidation
from cle.lifecycle.tags import STATE_RANK, move_state_tag
from cle.lifecycle.reasons import TopologyReason, validate_reason
from cle.lifecycle.topology import current_agents, render_diff, render_log, write_topology
from cle.oplog import OpLog, UnclassifiedOpError, classify_op, render_decision
from cle.runtime.container import ensure_container, load_containers, load_image, run_prompts
from cle.runtime.metrics_volume import read_events
from cle.runtime.mounts import Mount
from cle.store.backends import STORE_KINDS, StoreBackend, open_store
from cle.store.commits import Evidence, SourceSpec
from cle.store.objects import Block, content_hash

app = typer.Typer(help="CLE — Context Lifecycle Engine.")

_WINDOW = re.compile(r"^(\d+)([dh])$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
STATE_DIR_OPTION = typer.Option(Path(".cle"), "--state-dir", help="Persistent CLE state.")
STORE_OPTION = typer.Option(
    None, "--store", help=f"Persistence backend {STORE_KINDS} (default: file, or $CLE_STORE)."
)


EMBEDDER_OPTION = typer.Option(
    None, "--embedder",
    help=f"Detection vector space {EMBEDDER_KINDS} (default: stub, or $CLE_EMBEDDER). "
         "'cached' = real gemini-embedding-2 geometry, offline and free; "
         "'real' = live calls, costs money.",
)


@app.callback()
def cli(store: str = STORE_OPTION, embedder: str = EMBEDDER_OPTION) -> None:
    """The lifecycle CLI: evidence in, tags moved, everything logged."""
    # Set once, before any command runs, so every _store() call in this process
    # AND any subprocess (the dashboard) agree on the backend. Selecting it per
    # command would let two commands in one session write to different stores.
    if store is not None:
        if store.lower() not in STORE_KINDS:
            raise typer.BadParameter(f"--store must be one of {STORE_KINDS}, got {store!r}")
        os.environ["CLE_STORE"] = store.lower()
    # Same discipline for the vector space, and for a sharper reason: two
    # commands in one session detecting in different spaces would write
    # centroids that cannot be compared, into one topology that claims one
    # embedding config.
    if embedder is not None:
        if embedder.lower() not in EMBEDDER_KINDS:
            raise typer.BadParameter(
                f"--embedder must be one of {EMBEDDER_KINDS}, got {embedder!r}"
            )
        os.environ["CLE_EMBEDDER"] = embedder.lower()


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


def _configured_embedder():
    """The embedder this instance runs on — ONE source of truth.

    Every topology write declares it, so an inherited configuration that no
    longer matches raises instead of quietly asserting the original.
    """
    return open_embedder()


def _store(state_dir: Path) -> StoreBackend:
    # Never construct a backend directly — open_store is the single selection
    # point the dashboard also uses (see backends.open_store).
    return open_store(state_dir)


def _oplog(state_dir: Path):
    state_dir.mkdir(parents=True, exist_ok=True)
    sink = (state_dir / "log.jsonl").open("a")
    return OpLog(sink), sink


def _actor() -> str:
    # CLE_ACTOR overrides; otherwise the OS user — never a hardcoded name.
    return f"human:{os.getenv('CLE_ACTOR') or getpass.getuser()}"


def _resolve_image_hash(backend: StoreBackend, agent_or_image: str) -> tuple[str, str | None]:
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


def _seed_components(store: StoreBackend, components_dir: Path) -> None:
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
            embedder=_configured_embedder(), fingerprinter=fingerprinter,
            config=DetectorConfig(), oplog=oplog, actor=_actor(),
        )
        # Birth: the candidate tag and its topology entry, both carrying
        # the replay's pre_evidence (never more than that at birth) AND the
        # provenance of WHOSE usage produced the detection — the history's own
        # user, not the operator who happened to run the build.
        detected_for = all_messages[0].user_id
        move_state_tag(
            backend=store, agent=agent_name, image_hash=image.hash, from_state=None,
            to_state="candidate", pre_evidence=image.pre_evidence, oplog=oplog, actor=_actor(),
            on_behalf_of=detected_for,
        )
        write_topology(
            backend=store, path=state_dir / "topology.yaml", agent=agent_name,
            state="candidate", image_hash=image.hash,
            cause={"pre_evidence": image.pre_evidence.model_dump()}, oplog=oplog, actor=_actor(),
            on_behalf_of=detected_for,
            # First write of this topology: it is the only one that KNOWS the
            # vector space, so it is the one that records it. Later writes
            # inherit it from the parent record.
            embedding=embedding_config_for(_configured_embedder()),
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
    reason: str | None = typer.Option(
        None,
        help="Closed vocabulary (crosses into topology.yaml): "
             "substrate_drift | silence | cost_regression.",
    ),
    note: str | None = typer.Option(
        None,
        help="Free text. Logged locally, NEVER written to topology.yaml.",
    ),
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
        # DIRECTION, not destination. Testing only `to_state` would make a
        # DESCENT into `trial` or `candidate` load the image's birth
        # pre_evidence and record THAT as the cause, so a demotion would reach
        # topology labelled "caused by the replay proof of its own birth" while
        # the closed-vocabulary reason was dropped. A false field, not a
        # missing one.
        #
        # `from_state` is known here (read from current_agents above), so the
        # direction is computable at write time rather than derived later from
        # the chain diff.
        upward = STATE_RANK[to_state] > STATE_RANK[from_state]
        if evidence is None and upward and to_state in ("trial", "candidate"):
            pre_evidence = load_image(store, image_hash, oplog).pre_evidence
        move_state_tag(
            backend=store, agent=agent, image_hash=image_hash, from_state=from_state,
            to_state=to_state, evidence=evidence, pre_evidence=pre_evidence,
            reason=reason, note=note, oplog=oplog, actor=_actor(),
        )
        cause: dict = {}
        topology_reason = None
        if evidence is not None:
            cause["evidence"] = evidence.model_dump()
        elif pre_evidence is not None:
            cause["pre_evidence"] = pre_evidence.model_dump()
        else:
            # Downward move: accountability, not proof. The reason crosses the
            # boundary as a closed-vocabulary VALUE — `note` stays local, in the
            # oplog, which level 2 never reads.
            # `reason` cannot be None here: a downward move without one is
            # refused earlier ("downward moves must state a reason"), verified by
            # running it. The checker cannot see that guard from this branch.
            # pyrefly: ignore[bad-argument-type]
            topology_reason = TopologyReason(reason=reason)
        write_topology(
            backend=store, path=state_dir / "topology.yaml", agent=agent,
            state=to_state, image_hash=image_hash, cause=cause, oplog=oplog, actor=_actor(),
            embedding=embedding_config_for(_configured_embedder()),
            reason=topology_reason,
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
    decisions_only: bool = typer.Option(
        False, "--decisions-only",
        help="Only the lines where something was DECIDED, as sentences.",
    ),
    state_dir: Path = STATE_DIR_OPTION,
) -> None:
    """Op log (default) or topology history with provenance.

    Two READ views over the one write path: the default prints every line as
    raw JSON (the operator's view), `--decisions-only` prints just the
    decision-classified lines as sentences (the audit view). Nothing is
    written differently for either — see cle/oplog.py.
    """
    if target == "topology.yaml":
        typer.echo(render_log(_store(state_dir)))
        return
    log_path = state_dir / "log.jsonl"
    if not log_path.exists():
        typer.echo("(no log)")
        return
    lines = log_path.read_text().splitlines()
    if not decisions_only:
        for line in lines[-tail:]:
            typer.echo(line)
        return
    rendered = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        # An op nobody classified must not vanish from the audit view.
        try:
            if classify_op(record.get("op", "")) != "decision":
                continue
        except UnclassifiedOpError as unknown:
            rendered.append(f"[UNCLASSIFIED] {unknown}")
            continue
        rendered.append(render_decision(record))
    if not rendered:
        typer.echo("(no decisions logged)")
        return
    for sentence in rendered[-tail:]:
        typer.echo(sentence)


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
        # The live path may NOT write topology. A served model is not
        # deterministic at temperature 0 (measured: 3/3 runs produced distinct
        # fingerprints on an identical probe set), so every live revalidation
        # reports drift on an UNCHANGED substrate. Writing that would put a
        # `Persistence`, one of the three type-separated standards of proof,
        # into the single channel a population level reads. A fabricated proof
        # is worse than a missing one.
        #
        # The drift is still REPORTED: the operator sees it, and the oplog keeps
        # the technical line. Only the write and the demotion are withheld. The
        # stub path — everything the suite exercises — is untouched, and the
        # noise-floor measurement will lift or confirm this.
        if agent is not None and model_id in ("current", "live"):
            typer.echo(
                "live substrate: drift NOT written to topology and no demotion "
                "(this model is non-deterministic at temperature 0, so drift "
                "here is not evidence of substrate change)"
            )
        elif agent is not None:
            entry = current_agents(store)[agent]
            if entry["state"] in ("ephemeral", "pinned"):
                move_state_tag(
                    backend=store, agent=agent, image_hash=image_hash,
                    from_state=entry["state"], to_state="trial",
                    reason="substrate_drift",
                    note=f"fingerprint drift under {model_id}",
                    oplog=oplog, actor="engine:revalidator",
                )
                write_topology(
                    backend=store, path=state_dir / "topology.yaml", agent=agent,
                    state="trial", image_hash=image_hash,
                    cause={"persistence": persistence.model_dump()},
                    oplog=oplog, actor="engine:revalidator",
                    embedding=embedding_config_for(_configured_embedder()),
                )
                typer.echo(f"{agent}: {entry['state']} -> trial (auto-demoted)")
    finally:
        sink.close()


@app.command()
def decline(
    agent: str = typer.Argument(..., help="Candidate agent to refuse."),
    reason: str | None = typer.Option(
        None, help="Closed vocabulary: engine_disagrees | defer."
    ),
    note: str | None = typer.Option(None, help="Free text, logged locally."),
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
            # Same conditional unpack as `move_state_tag`: omitting the key is
            # the point, so a checker that cannot see the dict's keys reports a
            # possible mismatch on every named parameter of `emit`.
            # pyrefly: ignore[bad-argument-type]
            **({"reason": validate_reason(reason)} if reason else {}),
            # pyrefly: ignore[bad-argument-type]
            **({"note": note} if note else {}),
        )
        typer.echo(f"declined {agent} (was {entry['state']})")
    finally:
        sink.close()


@app.command()
def clean(
    state_dir: Path = STATE_DIR_OPTION,
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation (for scripts and CI)."
    ),
) -> None:
    """Reset the CLE state directory (deletes all persistent state).

    `shutil.rmtree` on a directory that is gitignored, so git cannot restore it,
    and that holds the only copy of the oplog, the store and the topology
    history.

    The confirmation names the RESOLVED path and what is in it, because the
    failure it prevents is not "meant to type something else" but "believed this
    path was the throwaway one". Note that `$CLE_STATE_DIR` does not redirect
    the CLI; only `--state-dir` does. `--yes` keeps `full_loop.sh`, the
    dashboard action and
    the demo working unattended.
    """
    import shutil

    if not state_dir.exists():
        typer.echo(f"CLE state directory {state_dir} does not exist.")
        return

    files = sum(1 for p in state_dir.rglob("*") if p.is_file())
    target = state_dir.resolve()
    if not yes:
        typer.echo(f"About to delete {target} ({files} files).")
        typer.echo("This is the only copy: the directory is gitignored, so git cannot restore it.")
        if not typer.confirm("Delete it?", default=False):
            typer.echo("Aborted. Nothing was deleted.")
            raise typer.Exit(code=1)

    shutil.rmtree(state_dir)
    typer.echo(f"CLE state directory {target} has been reset ({files} files deleted).")


if __name__ == "__main__":
    app()
