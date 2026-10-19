## 5. No dedicated vector storage is justified at this scale


Exhaustive `VECTOR_SEARCH` stays **under 3 s at one million vectors**. The knee
is not reached on latency; what grows is cost per query, for lack of
partitioning. The question left open when `WeaviateStore` was deleted has a
measured answer, and the answer is that the deletion cost nothing.

The BigQuery vector index itself is **not measured** (coverage 0% at end of
run). Stated as unmeasured, never estimated.

Related, and it is why BigQuery is not the state backend either: a point read of
a 15.4 Ko witness table takes a median **1 363 ms** and bills **10.5 Mo**.

Pinning key: `(2026-09-01, eca74ca+wt, bigquery:gemini-embedding-001:768, n/a)`.

```bash
uv run python examples/bigquery/vector_search_bench.py
```

---
