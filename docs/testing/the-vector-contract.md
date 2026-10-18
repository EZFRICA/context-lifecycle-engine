## The vector contract

Comparing two vectors is now a guarded operation, because it was not:

- **`cosine` is a cosine, measured, not assumed.** Both offline embedders
  return vectors of norm 1.000000 (measured, n=247 texts each: min=max=mean=1.000000
  across all 247 committed cache vectors and `HashedTokenEmbedder`), so the dot
  product is the cosine and the 0.46 / 0.6 / 0.775 thresholds share one scale.
- **`DimensionMismatchError`**: `zip` used to truncate to the shorter vector, so
  a 64-d stub centroid compared against a 768-d real embedding returned
  `-0.012148` and raised nothing. Unequal lengths now raise.
- **Space identity on the capture path**: `run_replay` refuses to run when the
  embedder's `embedder_id` differs from the trigger centroid's. The guard is on
  IDENTITY, not on dimension: two distinct real spaces of equal width would pass
  a length check and mean nothing.

**What the guard structurally cannot see.** `TriggerSpec.require_same_space`
compares two *stored* centroids and never sees the embedder actually running -
that was the gap. The new check closes it at the entry to `run_replay`, which
covers the three comparison sites inside it (`replay.py` selecting the target
cluster, computing capture, and beating incumbents) **only because every
centroid reaching them comes from the embedder checked at entry**. That is true
today; it is a flow property, not a structural one, and it would need
re-checking if a centroid ever entered by another path.

**Three sites, not one.** The first was found because a measurement happened to
cross it. The other two were found only by going looking. What an audit
finds is bounded by the pattern it searches for.
