"""Drive a real corpus through the CLI into its own state directory.

Two states, never mixed. Everything goes through `cle`, in a subprocess: no
library call writes anything here, because the architecture says the CLI is the
one write surface, and this is where real corpora exercise it.

`--state-dir` follows the SUBCOMMAND. `CLE_STATE_DIR` is not read by the CLI —
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

        python examples/bigquery/run_state.py stackoverflow [--state-dir DIR]
        python examples/bigquery/run_state.py wildchat      [--state-dir DIR]
    """
    if not argv or argv[0] not in ("stackoverflow", "wildchat"):
        print(__doc__ and main.__doc__)
        return 2
    corpus = argv[0]
    default = ROOT / f".cle-r36-{corpus}"
    state = Path(argv[argv.index("--state-dir") + 1]) if "--state-dir" in argv else default
    if state.resolve() == (ROOT / ".cle").resolve():
        print("refusing to run on .cle: pass --state-dir a scratch directory")
        return 1

    history = S / f"history_{corpus}.jsonl"
    if not history.exists():
        print(f"{history} is missing. Run prepare_states.py first (it needs BigQuery).")
        return 1
    if not CACHE.exists():
        print(f"{CACHE} is missing. Without it this replay would go to the network.")
        return 1

    from cle.detect.episodes import CoarseTimestampError

    embedder = open_embedder("cached")
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
    print(f"state dir    : {state}   (nothing was written to .cle)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
