## 9. Embedder substrate & centroid provenance (`cle/detect/embedders.py`)
- **Three implementations behind one Protocol**: `RealEmbedder` (a ~20-line
  google-genai adapter, **generation-only**: the sole thing needing a key and
  the network), `CachedEmbedder` (**the suite default**: dict lookup over
  committed vectors; a miss raises `CacheMissError` and never recomputes), and
  `StubEmbedder` (the deterministic v1 bag-of-tokens embedder).
- **Frozen vectors**: 247 distinct fixture texts embedded once and committed,
  so CI is offline and deterministic. Two consumers embed two *shapes* of text:
  clustering/replay embed an opener, the stability classifier embeds the
  follow-ups **joined**.
- **Cache key = `sha256(embedder_id \0 text)`**: a model change misses every
  key instead of silently reusing stale vectors. Integrity is a test: counts
  must match and no two distinct texts may share a vector.
- **Centroid provenance**: `TriggerSpec` records `embedder_id`, and
  `Image.hash` covers the trigger, so **two images built on different embedders
  have different hashes**. An embedder swap invalidates centroids exactly as a
  model swap invalidates a fingerprint, one layer deeper, and this one touches
  agent **identity**. Cross-space comparison raises `SpaceMismatchError`,
  enforced where routing actually compares.
- **No `model_version`**: the embedding API exposes no version signal distinct
  from the model id; a placeholder would give false drift-detection assurance.
