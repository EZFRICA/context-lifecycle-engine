"""Is BigQuery's `gemini-embedding-2` the same space as the engine's?

The question this repository carried from the start. Every corpus figure in
`docs/findings/` is labelled `bigquery:gemini-embedding-001:768` because the
bench could not run on the model the engine uses; cosine between those two
models is 0.040084. BigQuery made `gemini-embedding-2` generally available on
2026-10-05, so the question became measurable: embed texts whose engine-space
vectors are already committed, and compare.

Reads `examples/vectors.google-gemini-embedding-2-768.json` for the engine side.
BILLS: one embedding call per text on the BigQuery side (20 here), plus the
minimum query charge.

    uv run python examples/bigquery/space_identity_2.py
"""
import json, pathlib, sys
import numpy as np
sys.path.insert(0, ".")
from google.cloud import bigquery
from cle.detect.embedders import CachedEmbedder
from cle.detect.episodes import DetectorConfig, Message, segment


SAMPLE = 20                    # texts to compare; the cache holds 247


def main() -> int:
    """Everything happens here: importing this module must bill nothing and
    write nothing, which `tests/property/test_bench_imports_offline.py` enforces
    for every bench in this directory."""

    model = "emb_gemini_embedding_2"
    if "--model" in sys.argv:
        position = sys.argv.index("--model") + 1
        if position >= len(sys.argv):
            raise SystemExit("--model needs a remote model name")
        model = sys.argv[position]
    cached = CachedEmbedder.from_file()
    rows = [json.loads(l) for l in pathlib.Path("examples/prompt_history_gdg.jsonl").read_text().splitlines() if l.strip()]
    msgs = [Message(**{k: r.get(k) for k in ("text","ts","thread_id","user_id","requires_tool","tool_result")}) for r in rows]
    openers, seen = [], set()
    for e in segment(msgs, DetectorConfig()):
        t = e.messages[0].text
        if t in seen: continue
        try:
            cached.embed(t); openers.append(t); seen.add(t)
        except Exception: pass
        if len(openers) == SAMPLE: break
    print(f"  {len(openers)} textes présents dans le cache committé du moteur")

    c = bigquery.Client(project="context-lifecycle-engine")
    P = "context-lifecycle-engine.stackoverflow"
    frame = __import__("pandas").DataFrame({"content": openers})
    c.load_table_from_dataframe(frame, f"{P}.r41_identity_texts",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")).result()
    job = c.query(f"""
    CREATE OR REPLACE TABLE `{P}.r41_identity_emb` AS
    SELECT content, ml_generate_embedding_result AS v
    FROM ML.GENERATE_EMBEDDING(
      MODEL `{P}.{model}`,
      (SELECT content FROM `{P}.r41_identity_texts`),
      STRUCT(768 AS output_dimensionality, TRUE AS flatten_json_output))
    """, location="EU"); job.result()
    print(f"  modèle: {model}")
    print(f"  embeddings BigQuery produits (octets facturés: {job.total_bytes_billed:,})")

    sims, norms = [], []
    for r in c.query(f"SELECT content, v FROM `{P}.r41_identity_emb`", location="EU").result():
        bq = np.asarray(r["v"], dtype=float)
        norms.append(float(np.linalg.norm(bq)))
        engine = np.asarray(cached.embed(r["content"]), dtype=float)
        unit = bq / np.linalg.norm(bq) if np.linalg.norm(bq) else bq
        sims.append(float(np.dot(unit, engine)))
    sims = np.array(sims)
    print(f"\n  normes brutes BigQuery : min {min(norms):.6f}  max {max(norms):.6f}")
    print(f"  cosinus BigQuery vs moteur, mêmes textes :")
    print(f"    min {sims.min():.6f}   médiane {np.median(sims):.6f}   max {sims.max():.6f}")
    print(f"    identiques à 1e-6 : {int((sims > 1 - 1e-6).sum())}/{len(sims)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
