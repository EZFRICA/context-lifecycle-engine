## 9. Open decisions, status after P1

1. **SETTLED.** Episode segmentation without BOCPD: silence threshold +
   explicit markers, silence = 2× the user's median inter-message gap, floor
   30 min. Shipped as proposed.

2. **SETTLED, then REVISED by measurement.** Embedding model for clustering:
   a dedicated embedder, not the agents' model, confirmed, and for the stated
   reason (centroids must survive agent-model swaps). Measurement then added
   three things the proposal did not anticipate:
   - the embedder is a **substrate with provenance**, so `TriggerSpec` records
     `embedder_id` and cross-space comparison raises (§4);
   - the **clustering threshold is a property of the vector space**, not a
     global constant: bag-of-tokens puts same-domain text at ~0.2–0.4, a real
     sentence embedder at ~0.7–0.9. One number cannot serve both, so the
     threshold travels with `embedder_id` (0.6 for `stub:hashed64`, 0.775 for
     `google:gemini-embedding-2:768`);
   - **cosine is the wrong operator for contradiction.** It measures topical
     relatedness; opposing directives score 0.62–0.86 *because they are about
     the same thing*. The four-type contradiction taxonomy is therefore inert
     in a semantic space, which is why §5b exists. A signed/entailment operator
     is required and is **not** in v1 scope.
   Numbers: `docs/METRICS.md` (embedder upgrade run).

3. **SETTLED.** Probe set for `model_fingerprint`: 12 probes drawn from the
   cluster's replay window at build time, frozen into the image.
