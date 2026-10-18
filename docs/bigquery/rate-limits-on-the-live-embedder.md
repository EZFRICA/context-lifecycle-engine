## Rate limits on the live embedder

The AI Studio surface rate-limits, and it does so at a volume any real sweep
reaches. Measured before there was a backoff: comparing 186 cached vectors
against AI Studio lost **32 of them to 429s**, and an immediate second pass lost
**86**. The figure that came back described whatever survived the quota, and a
rerun described something else - an unrepeatable measurement, not a slow one.

`RealEmbedder` now retries a rate-limited call: **three attempts**, delay
doubling from 1 s and capped at 8 s, with full jitter so a batch that backs off
together does not re-collide on every wave. Only 429 / RESOURCE_EXHAUSTED is
retried; a 400 or a 403 fails on the first attempt, because retrying those turns
a clear error into a slow one.

Three attempts is deliberately short. A quota that is genuinely exhausted has to
surface while the operator is still watching, not an hour later, so the retry
rides out a burst and nothing more.

**If a sweep still hits the wall, change surface rather than wait.** The same
`gemini-embedding-2` is served by the Vertex API at location `global` under
application-default credentials - set `CLE_VERTEX_PROJECT` and the API-key branch
is bypassed entirely. Measured on the same 186 vectors: AI Studio returned 154 in
153 s; Vertex returned **186 in 37 s with zero failures**. Same space, cosine
1.000000 either way.

Note the error text is misleading here. AI Studio's 429 carries a
`cloud.google.com/vertex-ai/` URL, which reads as a Vertex failure; check
`CLE_VERTEX_PROJECT` before believing it.
