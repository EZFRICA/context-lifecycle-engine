"""Embed corpus C titles, once.

7,889 texts. The embedding calls are cheap; what costs is the table work around
them, which is why the cost ceiling is total billed bytes rather than per-query
bytes — a per-query ceiling bounds nothing while table creations go uncounted.

SPACE: `bigquery:gemini-embedding-001:768`. NOT the CLE's space (task 0.2
measured median cosine 0.037 between them), and NOT L2-normalised (norms ~0.58),
so every cosine below is computed with explicit normalisation.
"""
import time
import pandas as pd
from google.cloud import bigquery

import bqconfig
P = bqconfig.dataset()
c = bigquery.Client(project=bqconfig.project())

C = pd.read_parquet("examples/bigquery/data/corpus_c_windows.parquet")
texts = pd.DataFrame({"content": pd.unique(C.title.dropna())})
print(f"textes à embarquer : {len(texts):,}")

c.load_table_from_dataframe(texts, f"{P}.r23_c_texts", job_config=bigquery.LoadJobConfig(
    write_disposition="WRITE_TRUNCATE")).result()

t0 = time.perf_counter()
job = c.query(f"""
CREATE OR REPLACE TABLE `{P}.r23_c_emb` AS
SELECT content, ml_generate_embedding_result AS v
FROM ML.GENERATE_EMBEDDING(
  MODEL `{P}.emb_gemini_embedding_001`,
  (SELECT content FROM `{P}.r23_c_texts`),
  STRUCT(768 AS output_dimensionality, TRUE AS flatten_json_output))
""", location="EU")
job.result()
el = time.perf_counter() - t0
print(f"embedding : {el:.0f}s ({len(texts)/el:.0f} textes/s) | "
      f"{(job.total_bytes_billed or 0)/1e9:.3f} Go facturés")
