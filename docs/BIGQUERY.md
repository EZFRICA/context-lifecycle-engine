# Reproducing the corpus measurements

Everything in `docs/FINDINGS.md` was measured on BigQuery. This page is what you
need to run those commands on **your own** project. Nothing here is required to
use the CLE: the engine, the tests and the dashboard never touch BigQuery.

**These queries bill.** Costs are noted per step. Nothing runs by accident:
`bqconfig.py` has no defaults and raises if a variable is missing, so a script
cannot silently address whatever project you happen to be authenticated against.

---


- [1. What you need](bigquery/what-you-need.md) - `ML.GENERATE_EMBEDDING`, which reaches Vertex through a connection.
- [2. Dataset and connection](bigquery/dataset-and-connection.md) - export CLE_BQ_PROJECT=your-project
- [3. Remote models](bigquery/remote-models.md) - The benches address a model as `emb_<endpoint>` inside your dataset. Create the
- [4. Corpus A and B, Stack Overflow](bigquery/corpus-a-and-b-stack-overflow.md) - Public data, no download. Copy the two tables the extractors read into your own
- [5. Corpus C, WildChat](bigquery/corpus-c-wildchat.md) - Not public data. `allenai/WildChat-4.8M` is gated on Hugging Face: accept its
- [6. Reading what comes back](bigquery/reading-what-comes-back.md) - Parquet is columnar binary:
- [7. Replaying a corpus through the CLE, free](bigquery/replaying-a-corpus-through-the-cle-free.md) - Once `prepare_states.py` has written the histories and the vector cache exists,
- [Rate limits on the live embedder](bigquery/rate-limits-on-the-live-embedder.md) - The AI Studio surface rate-limits, and it does so at a volume any real sweep
- [Costs and pitfalls, measured](bigquery/costs-and-pitfalls-measured.md) - The first two are why BigQuery is not the CLE's state backend, and the third is
