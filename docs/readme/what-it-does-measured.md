## What it does, measured

Ten figures, each with its pinning key and reproduction command in
`docs/FINDINGS.md`. Read them together: several are one fact seen from two ends,
and publishing one without the other publishes half a measurement.

| what | figure |
|---|---|
| intents grouped, against Stack Overflow moderator ground truth | **32 / 48 = 67%**, against ~2% at random |
| the same run's cost | **`false_trigger_rate` 0.000**, `capture_rate` 1.000 (0.580 until replay stopped routing at a space-independent bar) |
| WildChat users with enough usage (≥40 turns, ≥30 days) | **0.34%** |
| of those, discarded by the coarse-timestamp guard | **29 of 40**, leaving ~0.08% of the corpus |
| occurrences of one intent for a first cluster | **~6**; **~10** for reliable recovery |
| episode count as a predictor | **nothing**. Occurrences per intent is the quantity |
| similarity floor, raw text / facets | **0.464** / **0.519 to 0.561** |
| dedicated vector storage | **not justified**: exhaustive search under 3 s at 1M vectors |
| cost of the facet boundary | **12.0 points** strict, **2.9** relaxed in the bench space; **11.6 / 2.5** local and **14.5 / 4.3** in the engine's own space - the ordering holds, the size does not |
| a free local space at level 1 (EmbeddingGemma-300m, ONNX, CPU) | **F 0.904** against **0.924** for the paid space, on the corpus neither was calibrated on |

Two readings that matter more than any single number:

**The engine addresses intensive users, and that is the design.** 0.08% sounds
like failure until you notice what the other 99.92% have in common: they have not
repeated anything. The CLE refuses to manufacture an agent for them. Being unable
to serve a user who has no recurring intent is the feature.

**The signal lives in the tail, never in the mean.** Cohesion inside a 90 day
window against pairs a year apart: factor **1.08 on the mean**, factor **12.9 on
the share above cosine 0.7**. Any population level aggregator must therefore be a
tail mechanism; one reading means would see ~0.55 everywhere and conclude nothing.

### Two spaces, and they are not the same model

The engine embeds on `gemini-embedding-2`, through AI Studio by API key or
through Vertex at location `global` by application-default credentials: the same
space either way, cosine 1.000000. It is **deterministic for embedding**, so
re-embedding the 186 fixture message texts reproduces their vectors in the
247-vector committed cache at cosine 1.000000; the generation model at T=0 is
not, which is why every facet figure names its frozen generation. The corpus benches run on BigQuery and go through
`gemini-embedding-001`, because when they were run BigQuery could not host
`gemini-embedding-2`. **Cosine between the two models on the same texts is
0.040084**, so every bench figure is conditioned on `gemini-embedding-001` and
says so. BigQuery made `gemini-embedding-2` generally available on 2026-10-05
(`docs/BIGQUERY.md`), so the gap is now closeable - by re-measuring in the new
space, never by relabelling the figures that were measured in the old one.

Numbers measured on fixtures rather than real corpora are in `docs/METRICS.md`.

---
