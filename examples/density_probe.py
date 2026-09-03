"""Is the detector's floor EPISODE DENSITY or OCCURRENCES PER INTENT?

Partitioning one corpus into N users means fewer episodes per user also means
fewer occurrences per intent. The two causes were confounded. This varies them
independently on the same corpus: a fixed episode budget spread over a varying
number of distinct intents.

Free: every GDG text is in the frozen cache, so `--embedder cached` costs
nothing and is the real gemini geometry.
"""
import collections
import json
import random
import sys
from pathlib import Path

EX = Path(__file__).resolve().parent
sys.path.insert(0, str(EX)); sys.path.insert(0, str(EX.parent))

from make_multiuser import BACKGROUND, planted_intent  # noqa: E402
from cle.detect.clusters import IntentClusterer  # noqa: E402
from cle.detect.embedders import open_embedder  # noqa: E402
from cle.detect.episodes import DetectorConfig, Message, segment  # noqa: E402

RECS = [json.loads(l) for l in (EX / "prompt_history_gdg.jsonl").read_text().splitlines()]
CFG = DetectorConfig()

BY_INTENT: dict[str, list[str]] = collections.defaultdict(list)
_seen = set()
for r in RECS:
    tid = r["thread_id"]
    if tid in _seen:
        continue
    _seen.add(tid)
    BY_INTENT[planted_intent(tid)].append(tid)
TASK_INTENTS = sorted(i for i in BY_INTENT if i not in BACKGROUND)
BY_THREAD: dict[str, list[dict]] = collections.defaultdict(list)
for r in RECS:
    BY_THREAD[r["thread_id"]].append(r)


def build_user(n_intents: int, n_episodes: int, seed: int, noise: int = 0):
    """A synthetic user: `n_episodes` threads spread over `n_intents` intents."""
    rng = random.Random(seed)
    intents = rng.sample(TASK_INTENTS, n_intents)
    per = max(1, n_episodes // n_intents)
    threads: list[str] = []
    for intent in intents:
        pool = list(BY_INTENT[intent]); rng.shuffle(pool)
        threads += pool[:per]
    if noise:
        pool = [t for i in BACKGROUND for t in BY_INTENT.get(i, [])]
        rng.shuffle(pool); threads += pool[:noise]
    rows = [r for t in threads for r in BY_THREAD[t]]
    rows.sort(key=lambda r: r["ts"])
    return rows


def measure(rows, embedder):
    msgs = [Message(**{k: r.get(k) for k in
                       ("text", "ts", "thread_id", "user_id", "requires_tool", "tool_result")})
            for r in rows]
    episodes = segment(msgs, CFG)
    clusterer = IntentClusterer(embedder, CFG)
    members: dict[int, list] = collections.defaultdict(list)
    for e in episodes:
        members[clusterer.assign(e)].append(e)
    sizes = sorted((len(g) for g in members.values()), reverse=True)
    return episodes, members, sizes


if __name__ == "__main__":
    emb = open_embedder("cached")
    print(f"{'intents':>8}{'eps':>6}{'occ/int':>9}{'clusters':>10}{'top':>5}{'>=3':>5}{'>=5':>5}")
    for n_int in (2, 3, 5, 7):
        for n_eps in (10, 20, 40, 80):
            tops, c3, c5, cl, ep = [], [], [], [], []
            for seed in range(5):
                rows = build_user(n_int, n_eps, seed)
                episodes, members, sizes = measure(rows, emb)
                ep.append(len(episodes)); cl.append(len(members)); tops.append(sizes[0])
                c3.append(sum(1 for s in sizes if s >= 3))
                c5.append(sum(1 for s in sizes if s >= 5))
            m = lambda v: sum(v) / len(v)
            print(f"{n_int:>8}{m(ep):>6.0f}{m(ep)/n_int:>9.1f}{m(cl):>10.1f}"
                  f"{m(tops):>5.1f}{m(c3):>5.1f}{m(c5):>5.1f}")
