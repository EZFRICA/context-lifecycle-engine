# Reproducing the corpus measurements

Everything in `docs/FINDINGS.md` was measured on BigQuery. This page is what you
need to run those commands on **your own** project. Nothing here is required to
use the CLE: the engine, the tests and the dashboard never touch BigQuery.

**These queries bill.** Costs are noted per step. Nothing runs by accident:
`bqconfig.py` has no defaults and raises if a variable is missing, so a script
cannot silently address whatever project you happen to be authenticated against.

---

## 1. What you need

* A Google Cloud project with billing enabled and the BigQuery API on.
* The **Vertex AI API** enabled in that project. The embedding benches call
  `ML.GENERATE_EMBEDDING`, which reaches Vertex through a connection.
* `gcloud` authenticated: `gcloud auth application-default login`.
* The measurement extras: `uv pip install -e ".[measure]"`.

Region matters and is not cosmetic. A US table is invisible to an EU query, and
the connection, the dataset and the models must agree. The published figures
were produced in **EU**; if you use another region, use it everywhere.

## 2. Dataset and connection

```bash
export CLE_BQ_PROJECT=your-project
export CLE_BQ_DATASET=cle                # any name; the corpus tables live here
export CLE_BQ_REGION=eu                  # lowercase, as the connection path wants
export CLE_BQ_CONNECTION=vertex_eu       # created below

bq --location=EU mk --dataset "${CLE_BQ_PROJECT}:${CLE_BQ_DATASET}"

bq mk --connection --location=EU --project_id="${CLE_BQ_PROJECT}" \
      --connection_type=CLOUD_RESOURCE "${CLE_BQ_CONNECTION}"
```

The connection runs as its own service account, and that account, not you, is
what calls Vertex. Read its id and grant it Vertex AI User, or every
`ML.GENERATE_EMBEDDING` fails with a permission error that names the connection
rather than you:

```bash
SA=$(bq show --format=prettyjson --connection \
     "${CLE_BQ_PROJECT}.${CLE_BQ_REGION}.${CLE_BQ_CONNECTION}" \
     | python -c 'import json,sys;print(json.load(sys.stdin)["cloudResource"]["serviceAccountId"])')

gcloud projects add-iam-policy-binding "${CLE_BQ_PROJECT}" \
  --member="serviceAccount:${SA}" --role=roles/aiplatform.user
```

Put the four variables in `.env` as well, so the scripts pick them up without an
export in every shell. `.env` is gitignored.

## 3. Remote models

The benches address a model as `emb_<endpoint>` inside your dataset. Create the
ones you intend to use:

```sql
CREATE OR REPLACE MODEL `your-project.cle.emb_gemini_embedding_001`
REMOTE WITH CONNECTION `your-project.eu.vertex_eu`
OPTIONS (ENDPOINT = 'gemini-embedding-001');
```

`model_bench.py` compares several, so repeat for `text_embedding_005` and
`text_multilingual_embedding_002` if you want the comparison.

> **`gemini-embedding-2` is not available here.** It has no BigQuery
> remote-model endpoint. It IS served by the Vertex API directly (location
> `global`, application-default credentials), so "not here" means "not through
> `ML.GENERATE_EMBEDDING`", not "not on Vertex". That is why no bench runs in the CLE's own vector
> space, and why every bench figure in `docs/FINDINGS.md` is labelled
> `bigquery:gemini-embedding-001:768`. Cosine between the two spaces on the same
> texts is **0.040084**: they are different models, not two views of one.

## 4. Corpus A and B, Stack Overflow

Public data, no download. Copy the two tables the extractors read into your own
dataset so they are in your region:

```bash
for t in posts_questions post_links; do
  bq --location=EU cp -f "bigquery-public-data:stackoverflow.${t}" \
     "${CLE_BQ_PROJECT}:${CLE_BQ_DATASET}.${t}"
done
```

`post_links` with `link_type_id = 3` is the moderator duplicate closure. That
column is the external ground truth behind the 67% figure: a human judgment the
detector never sees.

```bash
python examples/bigquery/extract_corpus_b.py      # matched controls
python examples/bigquery/extract_corpus_c.py      # 90-day recurrence windows
python examples/bigquery/build_zero_overlap.py    # pairs no lexical baseline sees
python examples/bigquery/embed_pairs.py           # bills: one embedding per text
```

## 5. Corpus C, WildChat

Not public data. `allenai/WildChat-4.8M` is gated on Hugging Face: accept its
terms, then `huggingface-cli login`. It is **real user prompts, consented for
research**. Treat it accordingly.

```bash
python examples/bigquery/load_wildchat.py         # streams from HF into BigQuery
python examples/bigquery/extract_cohort.py
python examples/bigquery/wildchat_density.py
```

`examples/bigquery/data/` and `examples/bigquery/states/` are gitignored in full,
and they must stay that way: the `episodes` and `text` columns hold raw prompts,
not summaries. Do not move a dump out of those directories.

## 6. Reading what comes back

Parquet is columnar binary:

```bash
python examples/bigquery/read_data.py                      # the catalogue
python examples/bigquery/read_data.py facets_pilot         # schema + first rows
python examples/bigquery/read_data.py facets_pilot --dump  # full text, to a file
```

## 7. Replaying a corpus through the CLE, free

Once `prepare_states.py` has written the histories and the vector cache exists,
this needs neither BigQuery nor an API key:

```bash
python examples/bigquery/run_state.py stackoverflow
python examples/bigquery/run_state.py wildchat
```

It reads `examples/bigquery/data/vectors.corpus_states.json` through
`$CLE_VECTOR_CACHE`, builds at `--model-id stub-model-1`, and refuses to run on
`.cle`. Reproduces the detection figures at zero cost.

---

## Rate limits on the live embedder

The AI Studio surface rate-limits, and it does so at a volume any real sweep
reaches. Measured before there was a backoff: comparing 186 cached vectors
against AI Studio lost **32 of them to 429s**, and an immediate second pass lost
**86**. The figure that came back described whatever survived the quota, and a
rerun described something else — an unrepeatable measurement, not a slow one.

`RealEmbedder` now retries a rate-limited call: **three attempts**, delay
doubling from 1 s and capped at 8 s, with full jitter so a batch that backs off
together does not re-collide on every wave. Only 429 / RESOURCE_EXHAUSTED is
retried; a 400 or a 403 fails on the first attempt, because retrying those turns
a clear error into a slow one.

Three attempts is deliberately short. A quota that is genuinely exhausted has to
surface while the operator is still watching, not an hour later, so the retry
rides out a burst and nothing more.

**If a sweep still hits the wall, change surface rather than wait.** The same
`gemini-embedding-2` is served by the Vertex API at location `global` under
application-default credentials — set `CLE_VERTEX_PROJECT` and the API-key branch
is bypassed entirely. Measured on the same 186 vectors: AI Studio returned 154 in
153 s; Vertex returned **186 in 37 s with zero failures**. Same space, cosine
1.000000 either way.

Note the error text is misleading here. AI Studio's 429 carries a
`cloud.google.com/vertex-ai/` URL, which reads as a Vertex failure; check
`CLE_VERTEX_PROJECT` before believing it.

## Costs and pitfalls, measured

| what | measured |
|---|---|
| point read of a 15.4 Ko table | median **1 363 ms**, bills **10.5 Mo** |
| column scan, unpartitioned 1M-row table | **6.27 Go** per query |
| exhaustive `VECTOR_SEARCH` at 1M vectors | **under 3 s** |
| embedding throughput | **269 texts/s** at scale |

The first two are why BigQuery is not the CLE's state backend, and the third is
why no dedicated vector store is justified. Partition and cluster your tables
before scanning them repeatedly.

**Norms.** `ML.GENERATE_EMBEDDING` returns vectors of norm **0.57 to 0.60**, not
1. The CLE's `cosine` is a raw dot product and assumes unit norm, so a vector
cache regenerated through BigQuery is refused on load by `assert_unit_norm`.
Normalise at your own boundary if you need to, and know that normalising does
not make those vectors the CLE's.
