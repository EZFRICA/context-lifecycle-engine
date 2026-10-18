## Measure A, the detector on an independent fixture (offline, free)

Run on `prompt_history_gdg.jsonl` (516 texts, all 516 in the frozen cache), the
GDG generator being one of the two declared independent of the detector. 246
episodes, 10 thread-prefix classes.

| space | threshold | clusters | purity | pure ≥80% | classes recovered |
|---|---|---|---|---|---|
| `stub:hashed64` | 0.6 | 63 | 0.882 | 53/63 | 9/10 |
| `google:gemini-embedding-2:768` | 0.775 | 40 | 0.935 | 36/40 | 9/10 |

**Three reservations, in the text and not in a footnote:**

1. **One threshold per space, not a curve.** Cluster count and purity are
   *jointly* determined by the threshold, so a single point cannot separate the
   effect of the space from the effect of the threshold. The result runs
   *against* the confound's expected direction (a higher threshold yielding
   *fewer* clusters), so it holds, but "better on every axis" is attached to
   "at this threshold" and does not travel without it.
2. **40 clusters for 10 classes is 4× over-fragmentation, in both spaces.** The
   real space fragments less (40 vs 63), not little. This table must not be read
   as "detection works".
3. **The missed class is `abandon`, identically in both spaces**: so it is a
   property of the data (abandoned episodes have no coherent opener), not
   information about the geometry.

**A separate script reproduces the PIPELINE, not the result:** 63 clusters under the stub and 40
under the real space at 0.775 match the before/after table above exactly, from a
script written months later. That establishes the published numbers are not
transcription errors, useful, and no more. It calls the same clusterer, so it
says nothing about whether the clustering is correct. The recovery figures do **not** compare -
this table's "classes" are thread-prefix classes at ≥80% purity, the older
table's are strict/lax recovery over 7 planted intents. Different definitions;
do not read 9/10 against 2/7.
