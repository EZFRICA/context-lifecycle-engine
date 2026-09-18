"""Measure WildChat's per-user structure across all 86 shards.

A head-slice cannot answer this. The stream is time-ordered, so a user with 50
conversations spread across the corpus shows up with one in any prefix; the
5,000-conversation probe reporting "median 3 turns/user" was measuring the
sample, not the corpus.

Parquet is columnar, so only the identity columns are parsed - the text is never
read. That makes the full-corpus answer cheap enough to actually get.
"""
import time
import pandas as pd

from cle.logs import configure_logging, get_logger

log = get_logger("wildchat_density")

REPO = "allenai/WildChat-4.8M"
COLS = ["conversation_hash", "hashed_ip", "timestamp", "turn", "language", "country"]
OUT = "examples/bigquery/data/wildchat_identity.parquet"


def main() -> None:
    # A script is an application: it configures logging, importing it does not
    # (cle/logs.py).
    configure_logging()
    # Imported here: `huggingface_hub` is not a declared dependency, so the
    # module must import without it and fail only when run.
    from huggingface_hub import hf_hub_download

    frames = []
    t0 = time.perf_counter()
    for i in range(86):
        # The Hub drops connections mid-run; already-fetched shards are cached, so
        # a retry is cheap and a resume is nearly free.
        for attempt in range(5):
            try:
                path = hf_hub_download(REPO, f"data/train-{i:05d}-of-00086.parquet",
                                       repo_type="dataset")
                break
            except Exception as error:
                if attempt == 4:
                    raise
                log.warning("shard %d: retry %d (%s)", i, attempt + 1, type(error).__name__)
                time.sleep(5)
        frames.append(pd.read_parquet(path, columns=COLS))
        if (i + 1) % 10 == 0:
            n = sum(len(f) for f in frames)
            print(f"  {i+1}/86 shards, {n:,} conversations, {time.perf_counter()-t0:.0f}s",
                  flush=True)

    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(OUT)
    print(f"\n{len(df):,} conversations | {df.hashed_ip.nunique():,} hashed_ip distincts")
    print(f"écrit -> {OUT}  ({time.perf_counter()-t0:.0f}s)")


if __name__ == "__main__":
    main()
