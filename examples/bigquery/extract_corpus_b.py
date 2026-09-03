"""Corpus B — the matched control for the self-duplicate pairs.

Same users as corpus A, same gap range, NOT linked by a duplicate. Without it,
corpus A measures nothing: a similarity distribution has no meaning until you
know what a non-duplicate pair from the same user scores.

The gap bound [1, 450] hours is corpus A's own p25..p95, measured, not chosen.
"""
from google.cloud import bigquery
import pandas as pd

import bqconfig
DS = f"`{bqconfig.dataset()}`"
c = bigquery.Client(project=bqconfig.project())
users = pd.read_parquet("examples/bigquery/data/corpus_a_selfdup.parquet").owner_user_id.unique().tolist()

Q = f"""
WITH capped AS (
  -- Cap questions per user BEFORE the self-join: a few users have thousands,
  -- and N^2 on them never converged. 20 bounds each user at 190 pairs.
  SELECT id, owner_user_id, title, creation_date,
         ROW_NUMBER() OVER (PARTITION BY owner_user_id ORDER BY RAND()) AS rn
  FROM {DS}.posts_questions
  WHERE owner_user_id IN UNNEST(@users)
),
mine AS (SELECT id, owner_user_id, title, creation_date FROM capped WHERE rn <= 20),
-- Normalised, deduplicated link keys so the exclusion is a HASH ANTI-JOIN.
-- A correlated NOT EXISTS against 8.4M rows ran for 7+ minutes twice.
linked AS (
  SELECT DISTINCT LEAST(post_id, related_post_id) AS lo,
                  GREATEST(post_id, related_post_id) AS hi
  FROM {DS}.post_links WHERE link_type_id = 3
),
pairs AS (
  SELECT x.owner_user_id, x.id AS id_a, y.id AS id_b,
         x.title AS title_a, y.title AS title_b,
         TIMESTAMP_DIFF(y.creation_date, x.creation_date, HOUR) AS gap_hours
  FROM mine x JOIN mine y ON x.owner_user_id = y.owner_user_id AND x.id < y.id
  WHERE TIMESTAMP_DIFF(y.creation_date, x.creation_date, HOUR) BETWEEN 1 AND 450
),
kept AS (
  SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.owner_user_id ORDER BY RAND()) AS pick
  FROM pairs p
  LEFT JOIN linked l ON l.lo = p.id_a AND l.hi = p.id_b
  WHERE l.lo IS NULL
)
SELECT owner_user_id, id_a, id_b, title_a, title_b, gap_hours FROM kept WHERE pick = 1
"""
job = c.query(Q, job_config=bigquery.QueryJobConfig(
    query_parameters=[bigquery.ArrayQueryParameter("users", "INT64", users)]))
df = job.result().to_dataframe()
df.to_parquet("examples/bigquery/data/corpus_b_control.parquet")
q = df.gap_hours.quantile([.25, .5, .75])
print(f"corpus B : {len(df):,} paires | {job.total_bytes_billed/1e9:.2f} Go facturés")
print(f"  utilisateurs : {df.owner_user_id.nunique():,}")
print(f"  écart (h) : p25={q[.25]:.1f} médiane={q[.5]:.1f} p75={q[.75]:.1f}")
