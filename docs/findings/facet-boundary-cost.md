## 6. The cost of the facet boundary


A facet is a one sentence description of what an agent does, standing in for the
episodes it was born from. Summarising loses information. How much depends
entirely on what you measure it against.

| comparison | agreement |
|---|---|
| centroid cosine, the upper bound available | **99.3%** |
| strict facet contract | 12.0 points below |
| relaxed facet contract | 2.9 points below |

**Measured on intent components, not on question pairs.** Comparing whole
questions answers a different question and gives a much larger loss; the object
being summarised has to be the object the agent is born from.

The internal gaps between the three rows are the finding. The absolute level is
conditioned on `gemini-embedding-001`.

## Measured in two more spaces, 2026-10-17

The question this section used to end on - whether the ordering holds in the
CLE's own space - needed the facet corpus re-embedded. It now has been, in both
directions: a local model that costs nothing, and the engine's own
`gemini-embedding-2`. The facets were NOT regenerated (a facet is data, not a
derivation, contract §c); one coordinate changed, the space.

Recall at a 10.1% false-positive budget, 276 components, each split into two
disjoint halves:

| method | `bigquery:gemini-embedding-001` | `onnx:embeddinggemma-300m-fp16:query` | `google:gemini-embedding-2` |
|---|---:|---:|---:|
| centroid, the upper bound | 99.3% | 97.8% | 98.2% |
| facet, strict contract | 87.3% | 86.2% | 83.7% |
| facet, relaxed contract | 96.4% | 95.3% | 93.8% |
| **cost of the strict boundary** | **12.0** | **11.6** | **14.5** |
| **cost of the relaxed boundary** | **2.9** | **2.5** | **4.3** |

**The ordering is robust; the size of the cost is not.** All three spaces agree
that the centroid leads, that the relaxed contract costs little, and that the
strict one costs several times more. What moves is the magnitude: the strict
boundary costs 11.6 points in the local space and 14.5 in the engine's own, a
spread of three points around the published 12.0. A reading that treated the
published gap as a property of the facet boundary alone would be wrong by that
much.

**The engine's space is the one where facets cost the most**, which is the
direction that matters for the deployment question: a layer that stores facets
instead of text gives up more inside the CLE than the bench space suggested.

Pinning keys: `(2026-10-17, 2a997be+wt, onnx:embeddinggemma-300m-fp16:query:768,
facets frozen under gemini-3.6-flash)` and `(2026-10-17, 2a997be+wt,
google:gemini-embedding-2:768, same facets)`. Both re-runs read the committed
`intent_facets_{strict,relaxed}_full.parquet` and bill nothing but the embedding
of 1,950 distinct texts.

```bash
uv run python examples/space_rerun_bench.py --space onnx     # free, local
CLE_VERTEX_PROJECT=<project> uv run python examples/space_rerun_bench.py --space real
```

The centroid costs nothing to compute and is the upper bound measured here, so
nothing in the facet path currently earns its keep against it.

Pinning key: `(2026-09-02, eca74ca+wt, bigquery:gemini-embedding-001:768,
gemini-3.6-flash for facet generation)`.

```bash
uv run python examples/bigquery/make_facets.py && uv run python examples/bigquery/intent_bench.py
```

---
