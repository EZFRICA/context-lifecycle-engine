"""Run one lifecycle per synthetic user — one state dir, one oplog, one topology.

CLE need. `make_multiuser.py` writes the histories; this drives each of them
through the CLI so that what lands on disk is produced by the same write path a
human uses. Every write goes through the CLI (invariant: the CLI is the one
write surface), so nothing here calls `move_state_tag` or `write_topology`.

TWO REAL SURFACES, and they are not equally priced:

  * DETECTION — `--embedder cached` is the real `gemini-embedding-2` geometry,
    read from the frozen 247-vector cache. Same `embedder_id` as `--embedder
    real`, same vectors, zero calls, because every GDG text is cached. Passing
    `real` here would spend one call per text to recompute vectors that are
    already committed, for a byte-identical result.
  * FINGERPRINT — `--model-id current` is the live model, and there is no cache
    for it. That is where the real substrate actually costs: 4 probes per build.

The live model is NOT deterministic at temperature 0 (measured, 3/3
runs, distinct fingerprints), so two runs of this script produce different image
hashes on the same input. That is the substrate, not a bug in this script.

Never writes to `.cle`: `--state-dir` is per-command and is passed on every
invocation, because `CLE_STATE_DIR` is not read by the CLI at all.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

EXAMPLES = Path(__file__).resolve().parent
ROOT = EXAMPLES.parent
sys.path.insert(0, str(ROOT))

from cle.detect.clusters import IntentClusterer  # noqa: E402
from cle.detect.embedders import open_embedder  # noqa: E402
from cle.detect.episodes import DetectorConfig, Message, segment  # noqa: E402

from make_multiuser import BACKGROUND, planted_intent  # noqa: E402

CLI = [sys.executable, "-m", "cle.cli.main"]


def _run(argv: list[str], state: Path, embedder: str) -> subprocess.CompletedProcess:
    """Invoke the CLI. `--embedder` is global (before the subcommand);
    `--state-dir` is per-command (after it)."""
    command = [*CLI, "--embedder", embedder, *argv, "--state-dir", str(state)]
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def _derive_spec(history: Path, embedder_kind: str, out_dir: Path) -> tuple[Path, str]:
    """Write an agent spec for this user's largest TASK cluster.

    The centroid is derived under the embedder that will run, and the spec
    declares it: a centroid is only meaningful in the space that produced it,
    and replay refuses a mismatch.
    """
    records = [json.loads(line) for line in history.read_text().splitlines()]
    config = DetectorConfig()
    messages = [
        Message(**{key: record.get(key) for key in
                   ("text", "ts", "thread_id", "user_id", "requires_tool", "tool_result")})
        for record in records
    ]
    episodes = segment(messages, config)
    embedder = open_embedder(embedder_kind)
    clusterer = IntentClusterer(embedder, config)

    members: dict[int, list] = {}
    for episode in episodes:
        members.setdefault(clusterer.assign(episode), []).append(episode)

    # Largest cluster whose majority intent is a TASK intent — background
    # traffic (`qa`, `noise`, `abandon`) is what an agent must NOT be born from.
    def majority(cluster) -> str:
        counts: dict[str, int] = {}
        for episode in cluster:
            intent = planted_intent(episode.messages[0].thread_id)
            counts[intent] = counts.get(intent, 0) + 1
        return max(counts, key=counts.get)

    task = [(cid, eps) for cid, eps in members.items() if majority(eps) not in BACKGROUND]
    if not task:
        raise SystemExit(f"{history.name}: no task cluster; the slice is too small")
    cluster_id, episodes_in = max(task, key=lambda pair: len(pair[1]))
    intent = majority(episodes_in)

    spec = out_dir / f"{history.stem}_agent.yaml"
    spec.write_text(yaml.safe_dump({
        "name": f"{intent}_agent",
        "detected_from": {"signal": "recurrence", "occurrences": len(episodes_in)},
        "components": [],
        "trigger": {
            "centroid": [round(v, 6) for v in clusterer.centroids[cluster_id]],
            "embedder_id": embedder.embedder_id,
        },
    }, sort_keys=False))
    return spec, intent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True,
                        help="Scratch directory; one subdirectory per user.")
    parser.add_argument("--embedder", default="cached", choices=("stub", "cached", "real"))
    parser.add_argument("--model-id", default="stub-model-1",
                        help="'current' = the LIVE model (4 calls per build).")
    parser.add_argument("--window", default="60d")
    args = parser.parse_args()

    root = Path(args.state_root).resolve()
    if root.name == ".cle" or root == ROOT / ".cle":
        raise SystemExit("refusing to run on .cle")
    root.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((EXAMPLES / "prompt_history_manifest.json").read_text())
    summary = {}
    calls = 0

    for user, info in manifest["users"].items():
        history = EXAMPLES / info["history"]
        state = root / user
        spec, intent = _derive_spec(history, args.embedder, root)

        built = _run(
            ["build", str(spec), "--replay-window", args.window,
             "--history", str(history), "--model-id", args.model_id],
            state, args.embedder,
        )
        if args.model_id in ("current", "live"):
            calls += 4  # one generateContent per probe
        if built.returncode != 0:
            print(f"{user}: build FAILED\n{built.stdout}{built.stderr}")
            summary[user] = {"intent": intent, "born": False}
            continue

        agent = f"{intent}_agent"
        _run(["tag", agent, "trial"], state, args.embedder)
        _run(["tag", agent, "ephemeral", "--cost-ratio", "0.7",
              "--occurrences", "4", "--closures", "success,success"],
             state, args.embedder)

        topology = yaml.safe_load((state / "topology.yaml").read_text())
        entry = topology["agents"][agent]
        summary[user] = {
            "intent": intent, "born": True, "agent": agent,
            "state": entry["state"], "cause": sorted(entry["cause"]),
            "embedder_id": topology["embedding"]["embedder_id"],
            "threshold": topology["embedding"]["cluster_threshold"],
            "topology_version": topology["version"],
            "oplog_lines": len((state / "log.jsonl").read_text().splitlines()),
        }

    print(f"{'user':8} {'agent':22} {'state':10} {'v':>3} {'oplog':>6}  embedder")
    for user, info in summary.items():
        if not info["born"]:
            print(f"{user:8} {info['intent']:22} (not born)")
            continue
        print(f"{user:8} {info['agent']:22} {info['state']:10} "
              f"{info['topology_version']:>3} {info['oplog_lines']:>6}  {info['embedder_id']}")
    print(f"\nstate root : {root}")
    print(f"live generateContent calls : {calls}")
    (root / "summary.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
