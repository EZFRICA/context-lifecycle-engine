# CLE Findings on Real Data

What the engine does when it is pointed at corpora nobody generated for it.
Everything in `docs/METRICS.md` is measured on fixtures; everything here is
measured on Stack Overflow (public) or WildChat (research-consented prompts).

**Every number below carries its pinning key and the command that produced it.**
A number without its command does not belong in this file.

Pinning key format: `(date, commit, embedder_id, model_id)`.

`eca74ca+wt` names the tree a measurement ran on: commit `eca74ca` plus the
working tree that became the change these docs ship with. **The commit to
reproduce against is the one that carries this file**, not a hash written
inside it: a hash written here is wrong the first time the history is rewritten,
and rewriting it before publishing is normal.

Two vector spaces appear throughout, and they are **not the same model**:

| space | surface | used for |
|---|---|---|
| `google:gemini-embedding-2:768` | AI Studio, or Vertex at `global` | the CLE itself |
| `bigquery:gemini-embedding-001:768` | Vertex, `ML.GENERATE_EMBEDDING` | the corpus benches |

When these benches ran, `gemini-embedding-2` was not available as a BigQuery
remote-model endpoint, so no BENCH could run in the CLE's own space: every bench
here goes through `ML.GENERATE_EMBEDDING`. Cosine between the two spaces, same
texts: **0.040084**. Read every bench figure as conditioned on
`gemini-embedding-001` - that conditioning is permanent for these numbers.
BigQuery added the endpoint as generally available on 2026-10-05; a run in it
would produce a THIRD column here, not an edit to this one.

> **This is narrower than it used to be stated.** Earlier passes wrote that the
> model is "AI Studio only". It is not: `gemini-embedding-2` is served by the
> Vertex API at location `global` (it 404s at `us-central1` and `europe-west1`),
> reachable with application-default credentials, and it returns the SAME
> vectors as AI Studio (cosine 1.000000 against the committed cache, n=3). What
> is unavailable is the BigQuery remote-model endpoint, which is a narrower
> thing than "Vertex". A bench in the CLE's own space is therefore possible; it
> just cannot be written as a BigQuery query.

---

## The findings, one file each

Each file carries its own pinning key `(date, commit, embedder_id, model_id)`
and the command that reproduces it. A figure belongs to the space that
produced it; re-measuring adds a file, it never edits one.

- [§1 Detection against external ground truth](findings/detection-ground-truth.md) - 32/48 intents grouped against Stack Overflow moderator closures, against ~2% at random.
- [§2 Addressable population](findings/addressable-population.md) - 0.34% of WildChat users have enough usage; the coarse-timestamp guard discards 29 of 40.
- [§3 What the detector's floor actually is](findings/detector-floor.md) - ~6 occurrences of one intent for a first cluster, ~10 for reliable recovery.
- [§4 The signal lives in the tail, never in the mean](findings/signal-in-the-tail.md) - Factor 1.08 on the mean, 12.9 on the share above cosine 0.7: a mean reading concludes nothing.
- [§5 No dedicated vector storage is justified at this scale](findings/vector-storage.md) - Exhaustive search stays under 3 s at 1M vectors.
- [§6 The cost of the facet boundary](findings/facet-boundary-cost.md) - 12.0 points strict, 2.9 relaxed, centroid upper bound 99.3%.
- [§6b Facets on the task level 2 actually does](findings/facets-at-level-2.md) - What a facet costs on cross-user grouping rather than on retrieval.
- [§6b-bis On real users, the ordering reverses](findings/real-users-ordering.md) - The method that wins on the fixture loses on real usage.
- [§6b-ter Stack Overflow across authors](findings/stack-overflow-authors.md) - Real users AND real labels: 61.1 raw text against 54.8 redacted facet at a 10.1% budget.
- [§6c The ranking of methods depends on where the threshold sits](findings/ranking-by-budget.md) - State the error budget or the ranking is unconditioned.
- [§6d Discovering intents without labels](findings/discovery-without-labels.md) - What a calibrated threshold does to three real corpora.
- [§7 The embedding model is deterministic; the generation model is not](findings/determinism.md) - Re-embedding reproduces the cache exactly; a facet generated at T=0 does not.
- [§8 A free local space at level 1](findings/local-space-onnx.md) - EmbeddingGemma-300m through ONNX: F 0.904 against 0.924, and a different partition.
- [§9 BigQuery and the engine finally share one space](findings/space-identity-bigquery.md) - cosine 1.000000 on the same texts: the disclosed gap that conditions every bench figure is closeable.
- [The comparison this file does NOT make](findings/comparison-not-made.md) - Why no table here ranks one architecture over another.
- [What none of this proves](findings/what-none-proves.md) - The limits that survive every figure above.

Fixture figures live in `docs/METRICS.md`; the contract they are read against
is `docs/BLUEPRINT.md`.
