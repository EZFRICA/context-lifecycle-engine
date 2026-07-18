"""`cle` command-line interface.

P1 exit criterion (CLAUDE.md): `cle build examples/weekly_recap_agent.yaml
--replay-window 30d` prints capture rate, false triggers, historical cost,
and the two hashes (source != image).

P1 ships `build` only; run|ps|tag|log|diff arrive with P2/P3.
"""

import getpass
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import typer
import yaml

from cle.build import build_image
from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.episodes import DetectorConfig, Message
from cle.oplog import OpLog
from cle.store.backends import InMemoryStore
from cle.store.commits import SourceSpec
from cle.store.objects import Block, content_hash

app = typer.Typer(help="CLE — Context Lifecycle Engine.")


@app.callback()
def cli() -> None:
    """Keeps `build` a subcommand even while it is P1's only one —
    run|ps|tag|log|diff join it in P2/P3."""

_WINDOW = re.compile(r"^(\d+)([dh])$")


class StubFingerprinter:
    """P1 substrate stand-in: deterministic hash over the probe set and a
    fixed model id. A live provider implements the same Protocol against
    real model outputs; the CLI swaps it by config in P2."""

    def __init__(self, model_id: str = "stub-model-1") -> None:
        self.model_id = model_id

    def fingerprint(self, probes) -> str:
        return content_hash({"model": self.model_id, "probes": list(probes)})


def _parse_window(label: str) -> timedelta:
    match = _WINDOW.match(label)
    if not match:
        raise typer.BadParameter(f"window must look like 30d or 48h, got {label!r}")
    value, unit = int(match.group(1)), match.group(2)
    return timedelta(days=value) if unit == "d" else timedelta(hours=value)


def _load_history(path: Path) -> list[Message]:
    messages = [
        Message.model_validate(json.loads(line))
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    return sorted(messages, key=lambda m: m.ts)


def _seed_components(store: InMemoryStore, components_dir: Path) -> None:
    # Simulates the populated store a running CLE would have: each YAML
    # file is one block plus the ref name the candidate uses.
    for component_file in sorted(components_dir.glob("*.yaml")):
        spec = yaml.safe_load(component_file.read_text())
        block = Block(kind=spec["kind"], payload=spec["payload"])
        store.put(block.hash, block.canonical_bytes())
        store.move_ref(spec["ref"], block.hash)


@app.command()
def build(
    source_path: Path = typer.Argument(..., help="Candidate source YAML (detector-written)."),
    replay_window: str = typer.Option("30d", help="Replay window, e.g. 30d or 48h."),
    history: Path = typer.Option(
        Path("examples/prompt_history.jsonl"), help="Prompt-history fixture (JSONL of messages)."
    ),
    components: Path = typer.Option(
        Path("examples/components"), help="Directory of block YAMLs to seed the store."
    ),
    log_file: Path | None = typer.Option(None, "--log", help="Append op log lines here (default stderr)."),
) -> None:
    """Three-stage build of a detected candidate against its own history."""
    window = _parse_window(replay_window)
    source = SourceSpec(yaml_raw=source_path.read_text())
    all_messages = _load_history(history)
    if not all_messages:
        typer.echo("history is empty; nothing to replay", err=True)
        raise typer.Exit(code=1)
    # Deterministic window anchor: the end of recorded history, not the
    # wall clock — replay must not depend on when you run it.
    window_end = all_messages[-1].ts
    window_messages = [m for m in all_messages if m.ts >= window_end - window]

    store = InMemoryStore()
    _seed_components(store, components)

    sink = log_file.open("a") if log_file else sys.stderr
    oplog = OpLog(sink)
    actor = f"human:{getpass.getuser()}"
    try:
        image = build_image(
            source=source,
            backend=store,
            messages=window_messages,
            window_label=replay_window,
            existing_triggers=[],
            embedder=HashedTokenEmbedder(),
            fingerprinter=StubFingerprinter(),
            config=DetectorConfig(),
            oplog=oplog,
            actor=actor,
        )
    except Exception as error:
        typer.echo(f"build failed: {error}", err=True)
        raise typer.Exit(code=1)
    finally:
        if log_file:
            sink.close()

    report = image.pre_evidence
    typer.echo(f"capture_rate        {report.capture_rate:.3f}")
    typer.echo(f"false_trigger_rate  {report.false_trigger_rate:.3f}")
    typer.echo(f"historical_cost     {report.historical_cost:.2f} iterations/episode")
    typer.echo(f"window              {report.window}  ({len(window_messages)} messages)")
    typer.echo(f"model_fingerprint   {image.model_fingerprint[:16]}…")
    typer.echo(f"source_hash         {image.source_hash}")
    typer.echo(f"image_hash          {image.hash}")
    typer.echo(f"two_hashes_distinct {image.hash != image.source_hash}")


if __name__ == "__main__":
    app()
