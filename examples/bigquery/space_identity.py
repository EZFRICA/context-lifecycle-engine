"""Is BigQuery's embedding space the CLE's space? (blocking for every bench)

Compared VECTOR BY VECTOR, never by model name. The CLE writes
`google:gemini-embedding-2:768` into every topology and calibrated 0.775 in it;
if BigQuery's vectors differ, that threshold applies to nothing measured here.
"""
import json, math, sys
from pathlib import Path
from google.cloud import bigquery

import bqconfig
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from cle.detect.embedders import cache_key, GEMINI_EMBEDDER_ID, VECTOR_CACHE

N = 20
DIM = int(sys.argv[1]) if len(sys.argv) > 1 else 768
ENDPOINT = sys.argv[2] if len(sys.argv) > 2 else "gemini_embedding_001"

cache = json.loads(Path(VECTOR_CACHE).read_text())["vectors"]
recs = [json.loads(l) for l in
        (Path("examples/prompt_history_gdg.jsonl")).read_text().splitlines()]
texts, cached = [], []
for r in recs:
    t = r.get("text")
    if not t:
        continue
    v = cache.get(cache_key(GEMINI_EMBEDDER_ID, t))
    if v is not None:
        texts.append(t); cached.append(v)
    if len(texts) == N:
        break

c = bigquery.Client(project=bqconfig.project())
Q = f"""
SELECT i, ml_generate_embedding_result AS v
FROM ML.GENERATE_EMBEDDING(
  MODEL `{bqconfig.dataset()}.emb_{ENDPOINT}`,
  (SELECT content, i FROM UNNEST(@texts) AS content WITH OFFSET AS i),
  STRUCT({DIM} AS output_dimensionality, TRUE AS flatten_json_output)
)
ORDER BY i
"""
# The models live in the EU dataset; a job defaulting to US cannot see them.
job = c.query(Q, location="EU", job_config=bigquery.QueryJobConfig(
    query_parameters=[bigquery.ArrayQueryParameter("texts", "STRING", texts)]))
bq = {r["i"]: list(r["v"]) for r in job.result()}

def norm(v): return math.sqrt(sum(x * x for x in v))
def cos(a, b):
    na, nb = norm(a), norm(b)
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0

print(f"endpoint={ENDPOINT}  output_dimensionality={DIM}  n={len(texts)}")
print(f"  dim cache = {len(cached[0])}   dim BigQuery = {len(bq[0])}")
if len(cached[0]) != len(bq[0]):
    print("  -> DIMENSIONS DIFFERENTES : le contrat vectoriel leverait.")
    raise SystemExit
sims = [cos(cached[i], bq[i]) for i in range(len(texts))]
norms = [norm(bq[i]) for i in range(len(texts))]
identical = sum(1 for i in range(len(texts))
                if all(abs(a - b) < 1e-6 for a, b in zip(cached[i], bq[i])))
print(f"  norme L2 BigQuery : min={min(norms):.6f} max={max(norms):.6f}")
print(f"  cosinus(cache, BigQuery) : min={min(sims):.6f} "
      f"med={sorted(sims)[len(sims)//2]:.6f} max={max(sims):.6f}")
print(f"  vecteurs identiques a 1e-6 : {identical}/{len(texts)}")
