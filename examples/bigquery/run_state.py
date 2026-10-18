"""Drive a real corpus through the CLI into its own state directory.

Two states, never mixed. Everything goes through `cle`, in a subprocess: no
library call writes anything here, because the architecture says the CLI is the
one write surface, and this is where real corpora exercise it.

`--state-dir` follows the SUBCOMMAND. `CLE_STATE_DIR` is not read by the CLI -
it is an export toward the dashboard subprocess, and mistaking that is how a
run writes into the operator's live state.

`--model-id stub-model-1` on every build: the default is `current`, the LIVE
model, so leaving it unset spends real calls. The fingerprinter is
not in this run's scope.
"""
import json, subprocess, sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
S = ROOT / "examples/bigquery/states"
CACHE = ROOT / "examples/bigquery/data/vectors.corpus_states.json"

import os
os.environ["CLE_VECTOR_CACHE"] = str(CACHE)
from cle.detect.clusters import IntentClusterer  # noqa: E402
from cle.detect.embedders import open_embedder  # noqa: E402
from cle.detect.episodes import DetectorConfig, Message, segment  # noqa: E402
from cle.logs import configure_logging, get_logger  # noqa: E402

log = get_logger("run_state")

CFG = DetectorConfig()
CLI = [sys.executable, "-m", "cle.cli.main"]


def cle(state: Path, *argv: str, embedder="cached"):
    out = subprocess.run([*CLI, "--embedder", embedder, *argv, "--state-dir", str(state)],
                         cwd=ROOT, capture_output=True, text=True,
                         env={**os.environ, "CLE_VECTOR_CACHE": str(CACHE)})
    return out


def load(history: Path):
    rows = [json.loads(l) for l in history.read_text().splitlines()]
    msgs = [Message(text=r["text"], ts=r["ts"], thread_id=r["thread_id"],
                    user_id=r["user_id"]) for r in rows]
    return msgs


def cluster(msgs, embedder):
    eps = segment(msgs, CFG)
    cl = IntentClusterer(embedder, CFG)
    assign = [cl.assign(e) for e in eps]
    return eps, assign, cl


def write_spec(path: Path, name: str, centroid, embedder_id: str, occ: int):
    path.write_text(yaml.safe_dump({
        "name": name,
        "detected_from": {"signal": "recurrence", "occurrences": occ},
        "components": [],
        "trigger": {"centroid": [round(float(v), 6) for v in centroid],
                    "embedder_id": embedder_id},
    }, sort_keys=False))
    return path


def main(argv: list[str]) -> int:
    """Replay one corpus through the CLI, OFFLINE.

    This is the reproduction command `docs/FINDINGS.md` publishes beside the
    detection figures. A number whose reproduction command does not run is a
    number nobody can check.

    Costs NOTHING. `$CLE_VECTOR_CACHE` points at the 4 542 vector cache paid for
    once, and `--model-id stub-model-1` keeps the fingerprinter off the
    live model (the default is `current`, which bills).

        uv run python examples/bigquery/run_state.py stackoverflow [--state-dir DIR]
        uv run python examples/bigquery/run_state.py wildchat      [--state-dir DIR]
    """
    # A script is an application: it configures logging, importing it does not
    # (cle/logs.py).
    configure_logging()
    if not argv or argv[0] not in ("stackoverflow", "wildchat"):
        print(__doc__ and main.__doc__)
        return 2
    corpus = argv[0]
    # The space is selectable because re-measuring in another one is now a thing
    # this repository does; `cached` stays the default so the command published
    # beside the figures keeps producing those figures.
    kind = argv[argv.index("--embedder") + 1] if "--embedder" in argv else "cached"
    default = ROOT / f".cle-r36-{corpus}"
    state = Path(argv[argv.index("--state-dir") + 1]) if "--state-dir" in argv else default
    if state.resolve() == (ROOT / ".cle").resolve():
        log.error("refusing to run on .cle: pass --state-dir a scratch directory")
        return 1

    history = S / f"history_{corpus}.jsonl"
    if not history.exists():
        log.error("%s is missing. Run prepare_states.py first (it needs BigQuery).", history)
        return 1
    if not CACHE.exists():
        log.error("%s is missing. Without it this replay would go to the network.", CACHE)
        return 1

    from cle.detect.episodes import CoarseTimestampError

    embedder = open_embedder(kind)
    msgs = load(history)

    # WildChat is a COHORT: `segment` refuses mixed user_ids, deliberately, since
    # the silence threshold is per user (a median gap across 40 people is not
    # anybody's median gap). So group first, and count what the coarse-timestamp
    # guard discards rather than hiding it: that share IS a published figure.
    by_user: dict[str, list] = {}
    for m in msgs:
        by_user.setdefault(m.user_id, []).append(m)

    sizes: dict[tuple[str, int], int] = {}
    eps, discarded = [], 0
    for user, rows in sorted(by_user.items()):
        try:
            user_eps, assign, _ = cluster(rows, embedder)
        except CoarseTimestampError:
            discarded += 1
            continue
        eps.extend(user_eps)
        for a in assign:
            if a is not None:
                sizes[(user, a)] = sizes.get((user, a), 0) + 1

    print(f"corpus       : {corpus}")
    # The threshold is a property of the SPACE, so read the scoped one. Printing
    # CFG.cluster_similarity_threshold shows the unscoped 0.6 default while the
    # clusterer is actually running at 0.775, which is a line that lies.
    from cle.detect.clusters import cluster_threshold_for
    threshold = cluster_threshold_for(embedder.embedder_id, CFG.cluster_similarity_threshold)
    print(f"space        : {embedder.embedder_id} @ {threshold}")
    print(f"messages     : {len(msgs)}")
    print(f"users        : {len(by_user)}"
          + (f"   discarded by the coarse-timestamp guard: {discarded}"
             f" ({discarded / len(by_user):.0%})" if discarded else ""))
    print(f"episodes     : {len(eps)}")
    print(f"clusters     : {len(sizes)}")
    for floor in (3, 6, 10):
        print(f"  >= {floor:2} occurrences : {sum(1 for n in sizes.values() if n >= floor)}")
    truth_path = S / "so_ground_truth.json"   # the sidecar prepare_states.py writes
    if corpus == "stackoverflow" and truth_path.exists():
        # The published headline, recomputed HERE rather than only in the
        # regression test, because the test pins ONE space and the whole point
        # of a second space is to read this number in it.
        truth = json.loads(truth_path.read_text())
        landed: dict[str, list] = {}
        all_eps, all_assign, _ = cluster(msgs, embedder)
        for episode, assignment in zip(all_eps, all_assign):
            component = truth.get(episode.opener)
            if component is not None and assignment is not None:
                landed.setdefault(component, []).append(assignment)
        present = {c: v for c, v in landed.items() if len(v) >= 2}
        grouped = {c: v for c, v in present.items() if len(set(v)) == 1}
        share = len(grouped) / len(present) if present else 0.0
        print(f"moderator-attested intents grouped : {len(grouped)}/{len(present)} "
              f"({share:.0%})   [~2% at random]")
        print("  the other half of this figure is false_trigger_rate; a detector "
              "collapsing everything scores 100% here")

        # So compute that half, here, in the space that just ran. It used to be
        # reconstructed by hand on the largest cluster, which is why `cle()` and
        # `write_spec()` sat unused in this file - and why the figure could not
        # be read in a second space without redoing that by hand.
        _, _, clusterer = cluster(msgs, embedder)
        biggest = max(sizes, key=sizes.get)
        state.mkdir(parents=True, exist_ok=True)
        spec = write_spec(state / "detected_agent.yaml", "detected_agent",
                          clusterer.centroids[biggest[1]], embedder.embedder_id,
                          sizes[biggest])
        built = cle(state, "build", str(spec), "--replay-window", "400d",
                    "--history", str(history), "--model-id", "stub-model-1",
                    embedder=kind)
        rates = [l.strip() for l in (built.stdout + built.stderr).splitlines()
                 if "capture_rate" in l or "false_trigger_rate" in l]
        print(f"largest cluster n={sizes[biggest]} rebuilt through `cle build`:")
        for line in rates or ["  (the build printed no rate - see the state dir)"]:
            print(f"  {line}")
    print(f"state dir    : {state}   (nothing was written to .cle)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
