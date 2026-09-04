"""Evaluate embedding models on the duplicate-pair bench.

The bench: 11,848 self-duplicate pairs judged by a moderator, 9,625
matched controls, a free lexical baseline at 62.2% / 10.1%, and
`gemini-embedding-001` at 73.9% recall at matched false positives.

No public leaderboard answers "which model is right for THIS task". This bench
does. Same corpus, same protocol, same presentation for every model — the only
thing that varies is the model.
"""
import time
import numpy as np
import pandas as pd

import bqconfig

D = "examples/bigquery/data"
BQ_MODELS = {
    "gemini-embedding-001": "emb_gemini_embedding_001",
    "text-embedding-005": "emb_text_embedding_005",
    "text-multilingual-embedding-002": "emb_text_multilingual_embedding_002",
}
LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def texts_for_bench() -> pd.DataFrame:
    A = pd.read_parquet(f"{D}/corpus_a_selfdup.parquet")
    B = pd.read_parquet(f"{D}/corpus_b_control.parquet")
    pairs = pd.concat([
        pd.DataFrame({"corpus": "A", "ta": A.dup_title.values, "tb": A.orig_title.values,
                      "gap": A.gap_hours.values, "jac": A.jaccard.values}),
        pd.DataFrame({"corpus": "B", "ta": B.title_a.values, "tb": B.title_b.values,
                      "gap": B.gap_hours.values, "jac": B.jaccard.values}),
    ], ignore_index=True)
    return pairs


def bq_embed(model: str, texts: list[str], dim: int = 768):
    """Embed through ML.GENERATE_EMBEDDING; returns (vectors, seconds)."""
    from google.cloud import bigquery
    c = bigquery.Client(project=bqconfig.project())
    P = bqconfig.dataset()
    t0 = time.perf_counter()
    q = f"""SELECT content, ml_generate_embedding_result AS v
            FROM ML.GENERATE_EMBEDDING(MODEL `{P}.{model}`,
              (SELECT content FROM UNNEST(@t) AS content),
              STRUCT({dim} AS output_dimensionality, TRUE AS flatten_json_output))"""
    rows = c.query(q, location="EU", job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("t", "STRING", texts)])).result()
    out = {r["content"]: np.asarray(r["v"], dtype=np.float32) for r in rows}
    return out, time.perf_counter() - t0


def local_embed(texts: list[str], batch: int = 128):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(LOCAL_MODEL, device="mps")
    t0 = time.perf_counter()
    # normalize_embeddings=False on purpose: this measures the model's
    # native norm rather than reading it from the library's convenience flag.
    V = model.encode(texts, batch_size=batch, show_progress_bar=False,
                     normalize_embeddings=False)
    return {t: v for t, v in zip(texts, V)}, time.perf_counter() - t0
