"""VECTOR_SEARCH cost and latency, to decide whether a vector store is needed.

The number that was missing to decide whether the CLE needs vector storage —
open since WeaviateStore was deleted. Reports the measurement; recommends
nothing.

Uses the 39,280 vectors already persisted in r23_emb. No new embedding call.
"""
import time
from google.cloud import bigquery

import bqconfig
P = bqconfig.dataset()
c = bigquery.Client(project=bqconfig.project())


def timed(sql: str, dry: bool = False):
    cfg = bigquery.QueryJobConfig(dry_run=dry, use_query_cache=False)
    t0 = time.perf_counter()
    job = c.query(sql, location="EU", job_config=cfg)
    if not dry:
        rows = list(job.result())
    else:
        rows = []
    return time.perf_counter() - t0, job, rows


# VECTOR_SEARCH allows only SELECT expressions and WHERE in its table
# arguments — no LIMIT. A row number is materialised once so size can be varied
# with a WHERE clause.
c.query(f"""CREATE OR REPLACE TABLE `{P}.r23_emb_rn` AS
            SELECT content, v, ROW_NUMBER() OVER (ORDER BY content) AS rn
            FROM `{P}.r23_emb`""", location="EU").result()


def search(n_base: int, k: int = 10) -> str:
    """Exhaustive VECTOR_SEARCH over the first `n_base` vectors, 5 queries."""
    return f"""
    SELECT query.content AS q, base.content AS hit, distance
    FROM VECTOR_SEARCH(
      (SELECT content, v FROM `{P}.r23_emb_rn` WHERE rn <= {n_base}), 'v',
      (SELECT content, v FROM `{P}.r23_emb_rn` WHERE rn <= 5), 'v',
      top_k => {k}, distance_type => 'COSINE')
    """


print(f"{'vecteurs':>10}{'latence (s)':>13}{'Go':>8}")
for n in (1000, 5000, 20000, 39280):
    lat, job, _ = timed(search(n))
    print(f"{n:>10}{lat:>13.2f}{(job.total_bytes_billed or 0)/1e9:>8.3f}")

print("\n=== index vectoriel ===")
t0 = time.perf_counter()
try:
    c.query(f"""CREATE OR REPLACE VECTOR INDEX r23_idx ON `{P}.r23_emb`(v)
                OPTIONS(index_type='IVF', distance_type='COSINE')""",
            location="EU").result()
    print(f"  CREATE VECTOR INDEX accepté en {time.perf_counter()-t0:.1f}s (construction asynchrone)")
except Exception as e:
    print(f"  refusé : {str(e)[:200]}")

rows = list(c.query(f"""
  SELECT index_name, coverage_percentage, last_refresh_time, disable_reason
  FROM `{P}.INFORMATION_SCHEMA.VECTOR_INDEXES`""", location="EU").result())
for r in rows:
    print(f"  {r.index_name}: couverture={r.coverage_percentage}% "
          f"refresh={r.last_refresh_time} raison={r.disable_reason}")
