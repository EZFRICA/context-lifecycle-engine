## Pinning key

Every figure below is a measurement, and a measurement without provenance is a
number. The embedding configuration has a key; so does every published
figure, which carries **(date, commit, embedder_id,
model_id)**.

| figure family | date | commit | embedder_id | model_id |
|---|---|---|---|---|
| threshold sweep, before/after table | 2026-07-24 | `19a0313`..`76efdc0` | `stub:hashed64` **and** `google:gemini-embedding-2:768` | n/a (no LLM on this path) |
| fingerprint determinism (3/3 distinct) | 2026-08-30 | `eca74ca` | n/a | `gemini-3.5-flash-lite` |
| Measure A (below) | 2026-08-30 | `eca74ca` + the tree that became this change | `stub:hashed64` / `google:gemini-embedding-2:768` | n/a |

**On the space of each figure.** The before/after table is already
space-annotated by its column headers, `v1 @0.6` is `stub:hashed64`, `real @…`
is `google:gemini-embedding-2:768`. So `capture 0.50 → 0.81` and
`false_trigger 0.0614 → 0.6316` are **cross-space** comparisons at a fixed
threshold, not stub-space figures. `0.775` was calibrated in the real space.
Every figure was checked against its label; none needed re-labelling, only pinning.

**`gemini-3.5-flash-lite` is an alias, not a pinned version.** Any figure
carrying it measures the provider's routing as much as the substrate. Recorded
as a limitation of the fingerprint figures, not fixed here.
