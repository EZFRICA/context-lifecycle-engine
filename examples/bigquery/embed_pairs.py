"""Embed corpus A and B, and score every pair by cosine.

Runs entirely inside BigQuery: texts are deduplicated, embedded once with
ML.GENERATE_EMBEDDING, and the pair cosine is computed in SQL. Nothing is
pulled back except two similarity columns.

SPACE: `bigquery:gemini-embedding-001:768`, NOT the CLE's
`google:gemini-embedding-2:768` — task 0.2 measured a median cosine of 0.037
between the two spaces for the same text. `0.775` does not apply here.
"""
import time
import pandas as pd
from google.cloud import bigquery

import bqconfig
P = bqconfig.dataset()
c = bigquery.Client(project=bqconfig.project())
D = "examples/bigquery/data"

A = pd.read_parquet(f"{D}/corpus_a_selfdup.parquet")
B = pd.read_parquet(f"{D}/corpus_b_control.parquet")
pairs = pd.concat([
    pd.DataFrame({"corpus": "A", "k": range(len(A)),
                  "ta": A.dup_title.values, "tb": A.orig_title.values,
                  "gap": A.gap_hours.values, "jac": A.jaccard.values}),
    pd.DataFrame({"corpus": "B", "k": range(len(B)),
                  "ta": B.title_a.values, "tb": B.title_b.values,
                  "gap": B.gap_hours.values, "jac": B.jaccard.values}),
], ignore_index=True)

c.load_table_from_dataframe(pairs, f"{P}.r23_pairs", job_config=bigquery.LoadJobConfig(
    write_disposition="WRITE_TRUNCATE")).result()

n_texts = pd.unique(pd.concat([pairs.ta, pairs.tb]).dropna()).size
print(f"paires : {len(pairs):,}  |  textes distincts a embarquer : {n_texts:,}")

t0 = time.perf_counter()
c.query(f"""
CREATE OR REPLACE TABLE `{P}.r23_texts` AS
SELECT DISTINCT content FROM (
  SELECT ta AS content FROM `{P}.r23_pairs` UNION ALL
  SELECT tb AS content FROM `{P}.r23_pairs`) WHERE content IS NOT NULL
""", location="EU").result()
c.query(f"""
CREATE OR REPLACE TABLE `{P}.r23_emb` AS
SELECT content, ml_generate_embedding_result AS v
FROM ML.GENERATE_EMBEDDING(
  MODEL `{P}.emb_gemini_embedding_001`,
  (SELECT content FROM `{P}.r23_texts`),
  STRUCT(768 AS output_dimensionality, TRUE AS flatten_json_output))
""", location="EU").result()
elapsed = time.perf_counter() - t0
print(f"embedding : {elapsed:.0f}s  ({n_texts/elapsed:.0f} textes/s)")

job = c.query(f"""
SELECT p.corpus, p.k, p.gap, p.jac,
       1 - ML.DISTANCE(ea.v, eb.v, 'COSINE') AS cos
FROM `{P}.r23_pairs` p
JOIN `{P}.r23_emb` ea ON ea.content = p.ta
JOIN `{P}.r23_emb` eb ON eb.content = p.tb
""", location="EU")
out = job.result().to_dataframe()
out.to_parquet(f"{D}/pairs_scored.parquet")
print(f"scoré : {len(out):,} paires | {job.total_bytes_billed/1e9:.2f} Go")
