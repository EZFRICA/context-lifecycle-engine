"""Load WildChat-4.8M into BigQuery, in the shape the CLE detector consumes.

WHY A SECOND SHAPE. The noise problem measured on the synthetic corpus is a
`make_gdg_fixture.py` artefact: its background categories draw from banks of
8-12 phrases, so a background cluster is the same sentence repeated verbatim
(0.33 distinct openers, against 1.00 for task intents). Real data has none of
that — 0 duplicate titles in 7,898 Stack Overflow questions. What is missing is
a real corpus with PER-USER episode structure. WildChat has it: `hashed_ip` is
the closest thing to a user, and each conversation is a thread of turns.

FOUR THINGS THE STRAIGHTFORWARD LOADER GETS WRONG:

1. LOCATION. A dataset created without `location` lands in US. The Vertex
   connection and `stackoverflow` are in **EU**, and a US table is invisible to
   `ML.GENERATE_EMBEDDING` through an EU connection, which is where a US table fails.
   The dataset is created in EU explicitly.

2. EXPLICIT SCHEMA, never autodetect. Loading batch by batch with autodetect
   lets batch N infer a different schema from batch N-1 (a column that is all
   null in one batch and typed in the next), which fails mid-run after hours.

3. THE MODERATION BLOBS ARE DROPPED. `openai_moderation` and
   `detoxify_moderation` are deeply nested, variable-key structures; handing
   them to `load_table_from_dataframe` makes BigQuery infer an enormous nested
   schema and is where a naive load stalls. They are not needed for episode or
   recurrence work. Dropping them is a choice, and it is stated rather than
   silent.

4. ONE ROW PER USER TURN, not one per conversation. The detector consumes
   `Message(text, ts, thread_id, user_id)`. Turn-level rows give that directly;
   conversation-level rows would need unnesting on every read.

PRIVACY, stated because it is not obvious. WildChat carries `hashed_ip`,
`state`, `country` and request headers alongside real user text. That is a
quasi-identifier set. It is loaded here for MEASUREMENT only. Invariant 4 —
a population level reads topology history, never user text — applies to
anything built on top of this, and nothing in this file writes to `.cle` or to
any topology.
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd
from google.cloud import bigquery

import bqconfig
PROJECT = bqconfig.project()
DATASET = f"{PROJECT}.wildchat"

TURN_SCHEMA = [
    bigquery.SchemaField("conversation_hash", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("hashed_ip", "STRING"),          # the user proxy
    bigquery.SchemaField("conversation_ts", "TIMESTAMP"),
    bigquery.SchemaField("turn_index", "INTEGER"),        # 0-based, user turns only
    bigquery.SchemaField("role", "STRING"),
    bigquery.SchemaField("content", "STRING"),
    bigquery.SchemaField("language", "STRING"),
    bigquery.SchemaField("country", "STRING"),
    bigquery.SchemaField("model", "STRING"),
    bigquery.SchemaField("toxic", "BOOLEAN"),
    bigquery.SchemaField("redacted", "BOOLEAN"),
]


def flatten(row: dict, user_only: bool) -> list[dict]:
    """One record per turn. `created`/`timestamp` are null per turn in this
    dataset, so the conversation timestamp plus the turn index is the only
    ordering available — carried explicitly rather than invented."""
    out = []
    index = 0
    for turn in row.get("conversation") or []:
        role = turn.get("role")
        if user_only and role != "user":
            continue
        out.append({
            "conversation_hash": row.get("conversation_hash"),
            "hashed_ip": row.get("hashed_ip"),
            "conversation_ts": row.get("timestamp"),
            "turn_index": index,
            "role": role,
            "content": turn.get("content"),
            "language": row.get("language"),
            "country": row.get("country"),
            "model": row.get("model"),
            "toxic": bool(row.get("toxic")),
            "redacted": bool(row.get("redacted")),
        })
        index += 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50_000,
                        help="Conversations to read. 0 = the whole 4.8M.")
    parser.add_argument("--batch", type=int, default=20_000, help="Rows per load job.")
    parser.add_argument("--table", default="turns")
    parser.add_argument("--all-roles", action="store_true",
                        help="Keep assistant turns too (default: user turns only).")
    args = parser.parse_args()

    from datasets import load_dataset

    client = bigquery.Client(project=PROJECT)
    table_id = f"{DATASET}.{args.table}"

    # Truncate ONCE, up front, then append. Deciding the disposition from the
    # loop counter works only by an off-by-one that breaks the moment the batch
    # size changes meaning.
    base = bigquery.LoadJobConfig(schema=TURN_SCHEMA, write_disposition="WRITE_TRUNCATE")
    append = bigquery.LoadJobConfig(schema=TURN_SCHEMA, write_disposition="WRITE_APPEND")
    config = base

    stream = load_dataset("allenai/WildChat-4.8M", split="train", streaming=True)
    batch: list[dict] = []
    conversations = turns = 0

    def flush(rows: list[dict], cfg) -> None:
        frame = pd.DataFrame(rows, columns=[f.name for f in TURN_SCHEMA])
        frame["conversation_ts"] = pd.to_datetime(frame["conversation_ts"], utc=True)
        client.load_table_from_dataframe(frame, table_id, job_config=cfg).result()

    for row in stream:
        batch.extend(flatten(row, user_only=not args.all_roles))
        conversations += 1
        if len(batch) >= args.batch:
            flush(batch, config); config = append
            turns += len(batch); batch = []
            print(f"  {conversations:,} conversations / {turns:,} tours", flush=True)
        if args.limit and conversations >= args.limit:
            break

    if batch:
        flush(batch, config)
        turns += len(batch)

    table = client.get_table(table_id)
    print(f"\n{table_id}: {table.num_rows:,} lignes, {table.num_bytes/1e6:.1f} Mo")
    print(f"lu : {conversations:,} conversations -> {turns:,} tours utilisateur")


if __name__ == "__main__":
    sys.exit(main())
