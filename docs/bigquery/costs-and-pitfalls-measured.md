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
