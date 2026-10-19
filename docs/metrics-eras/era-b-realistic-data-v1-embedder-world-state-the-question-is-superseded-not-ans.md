## `world_state`: the question is superseded, not answered

Injecting the same moderate contradiction into the tool-bearing `events` intent:

| embedder | directive cosine | classified as | cluster after injection |
|---|---|---|---|
| stub (v1) | 0.1140 | `world_state` (absorbed) | unstable=True, intra=3 |
| real | **0.7197** | **not divergent at all** | unstable=False, intra=0 |

Under v1 the narrow rule-level blindness was real (a moderate flip co-occurring
with a differing `tool_result` got absorbed). Under the real embedder the pair
never registers as divergent, so it never reaches the rule: **the rule is
unreachable, not fixed**. v1 at least saw divergence and mis-attributed some of
it; the real embedder sees none.


---

# Two traps in building the vector cache

Both are silent, both are now guarded, and both are worth knowing before
regenerating the cache.

1. **A list of contents is ONE document, not a batch.** `gemini-embedding-2`
   treats `contents=[...]` as a single multi-part document and returns a single
   embedding, so 190 texts come back as 2 vectors with nothing raised. The only
   visible symptom is file size: 34 KB where ~3 MB was expected. Embed one
   content per call (190 calls, 62.7 s). Guarded by
   `test_vector_cache_has_one_distinct_vector_per_text`, which asserts the count
   matches the texts and that no two distinct texts share a vector.
2. **Two consumers embed two SHAPES of text.** Clustering and replay embed an
   opener; the stability classifier embeds the follow-ups **joined** into one
   string, which is no single message. A cache covering only message texts
   raises `CacheMissError` part way through a run. For the shipped fixtures that
   is the difference between 190 and 247 vectors.

---
