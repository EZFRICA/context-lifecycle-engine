"""Put the two real corpora into CLI-consumable shape.

TWO STATES, NEVER MIXED. They test different capacities and a mixed topology
would say nothing about either:

  A. Stack Overflow — reformulation. A connected component of the self-duplicate
     graph is one intent a MODERATOR attested. Split in two disjoint halves, so
     the measurable question is: do the two halves land in the SAME detected
     cluster?
  B. WildChat — recurrence on real background. 40 dense monolingual users.

Both are written as `prompt_history` JSONL, the format `cle build --history`
reads, so the texts go through the CLI and not through a measurement script.

Empty texts are FILTERED AND COUNTED here (task 1ter). The embed path has three
guards — CacheMissError, dimension, norm — and none applies before the network:
they check what comes back, not what goes out. One empty string in 4,448 aborts
a whole batch from the API side.
"""
import json, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(".env")

sys.path.insert(0, ".")
import pandas as pd  # noqa: E402
from cle.detect.embedders import GEMINI_EMBEDDER_ID, RealEmbedder, cache_key  # noqa: E402

D = Path("examples/bigquery/data")
OUT = Path("examples/bigquery/states"); OUT.mkdir(parents=True, exist_ok=True)


def stack_overflow(n_components: int = 40):
    comp = json.load(open(D / "intent_components.json"))
    title = json.load(open(D / "intent_titles.json"))
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows, truth, clock = [], {}, 0
    for key, ids in list(comp.items())[:n_components]:
        texts = [title[str(i)] for i in ids if str(i) in title and title[str(i)]]
        if len(texts) < 3:
            continue
        cut = max(1, len(texts) // 2)
        for half, chunk in (("a", texts[:cut]), ("b", texts[cut:])):
            for t in chunk:
                clock += 1
                rows.append({"text": t, "user_id": "so",
                             "ts": (base + timedelta(hours=clock)).isoformat(),
                             "thread_id": f"{key}-{half}-{clock}"})
                truth[t] = f"{key}#{half}"
    return rows, truth


def wildchat(n_users: int = 40):
    t = pd.read_parquet(D / "wildchat_cohort_turns.parquet",
                        columns=["hashed_ip", "conversation_hash", "ts", "turn_index", "text"])
    idx = pd.read_parquet(D / "wildchat_cohort_index.parquet")
    mono = set(idx[(idx.langs == 1) & (idx.convs.between(25, 250))].index)
    users = [u for u in t.hashed_ip.unique() if u in mono][:n_users]
    sub = t[t.hashed_ip.isin(users)].sort_values(["hashed_ip", "ts", "turn_index"])
    rows = []
    for r in sub.itertuples():
        text = str(r.text) if r.text is not None else ""
        rows.append({"text": text[:2000], "user_id": str(r.hashed_ip),
                     "ts": pd.Timestamp(r.ts).isoformat(),
                     "thread_id": str(r.conversation_hash)})
    return rows


if __name__ == "__main__":
    so_rows, so_truth = stack_overflow()
    wc_rows = wildchat()
    stats = {}
    for name, rows in (("stackoverflow", so_rows), ("wildchat", wc_rows)):
        kept = [r for r in rows if r["text"].strip()]
        stats[name] = {"total": len(rows), "empty": len(rows) - len(kept)}
        (OUT / f"history_{name}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in kept) + "\n")
        print(f"{name}: {len(kept)} messages ({stats[name]['empty']} vides écartés), "
              f"{len({r['text'] for r in kept})} textes distincts", flush=True)
    json.dump(so_truth, open(OUT / "so_ground_truth.json", "w"))

    texts = sorted({r["text"] for name in ("stackoverflow", "wildchat")
                    for r in json.loads("[" + ",".join(
                        (OUT / f"history_{name}.jsonl").read_text().splitlines()) + "]")})
    print(f"\nà embarquer : {len(texts)} textes distincts", flush=True)
    e, t0, vectors = RealEmbedder(), time.perf_counter(), {}
    for i, txt in enumerate(texts):
        vectors[cache_key(GEMINI_EMBEDDER_ID, txt)] = list(e.embed(txt))
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(texts)}  {time.perf_counter()-t0:.0f}s", flush=True)
    json.dump({"embedder_id": GEMINI_EMBEDDER_ID, "vectors": vectors},
              open(D / "vectors.corpus_states.json", "w"))
    print(f"\n{len(vectors)} vecteurs en {time.perf_counter()-t0:.0f}s "
          f"-> {D}/vectors.corpus_states.json")
