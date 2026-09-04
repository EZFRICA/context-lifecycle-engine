"""Extract the WildChat cohort's text.

Cohort: >=40 user turns AND >=30 days of activity, from the full-corpus identity
pass — 6,161 of 1,833,730 hashed_ip (0.34%). Below that bar there is too little
usage for a recurrence to exist at all (~6-10 occurrences of one intent
before a cluster forms).

Written PER SHARD. A first attempt held everything in memory, reached 80/86, and
lost all of it when the process died: 17 minutes of work for nothing. Each shard
is now flushed as it is read, so an interruption costs one shard.

Shards are already in the HF cache — this downloads nothing. Only USER turns are
kept: assistant text is the model's output, not the user's usage.
"""
import time
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download

REPO = "allenai/WildChat-4.8M"
D = Path("examples/bigquery/data")
CH = D / "cohort_chunks"
CH.mkdir(parents=True, exist_ok=True)

ident = pd.read_parquet(D / "wildchat_identity.parquet")
ident["ts"] = pd.to_datetime(ident.timestamp, utc=True, errors="coerce")
g = ident.groupby("hashed_ip")
per = pd.DataFrame({"turns": g.turn.sum(),
                    "span": (g.ts.max() - g.ts.min()).dt.days,
                    "langs": g.language.nunique(),
                    "convs": g.size()})
cohort = per[(per.turns >= 40) & (per.span >= 30)]
cohort.to_parquet(D / "wildchat_cohort_index.parquet")
keep = set(cohort.index)
print(f"cohorte : {len(keep):,} utilisateurs", flush=True)

t0 = time.perf_counter()
for i in range(86):
    out = CH / f"turns_{i:05d}.parquet"
    if out.exists():
        continue
    path = hf_hub_download(REPO, f"data/train-{i:05d}-of-00086.parquet", repo_type="dataset")
    df = pd.read_parquet(path, columns=["conversation_hash", "hashed_ip", "timestamp",
                                        "conversation", "language"])
    df = df[df.hashed_ip.isin(keep)]
    rows = []
    for r in df.itertuples():
        conv = r.conversation if r.conversation is not None else []
        idx = 0
        for t in conv:
            if t.get("role") != "user":
                continue
            rows.append((r.hashed_ip, r.conversation_hash, r.timestamp, idx,
                         r.language, t.get("content")))
            idx += 1
    pd.DataFrame(rows, columns=["hashed_ip", "conversation_hash", "ts", "turn_index",
                                "language", "text"]).to_parquet(out)
    print(f"  {i+1}/86  {len(rows):,} tours  {time.perf_counter()-t0:.0f}s", flush=True)

frames = [pd.read_parquet(f) for f in sorted(CH.glob("turns_*.parquet"))]
allt = pd.concat(frames, ignore_index=True)
allt.to_parquet(D / "wildchat_cohort_turns.parquet")
print(f"\n{len(allt):,} tours | {allt.hashed_ip.nunique():,} utilisateurs "
      f"| {time.perf_counter()-t0:.0f}s")
