## 2. Detection, the first pillar (`cle/detect`)
- **Episode segmentation**: splits history on silence (> 2× the user's median
  inter-message gap, floor 30 min) and explicit markers. Closure classification
  (`success` / `reformulated` / `abandoned`); abandoned episodes are excluded
  from cost baselines (anti-Goodhart).
- **Incremental intent clustering**: openers embedded behind the `Embedder`
  Protocol, clustered by cosine. The threshold is a property of the **vector
  space**, not a global default, and travels with `embedder_id`: **0.6** for
  `stub:hashed64`, **0.775** for `google:gemini-embedding-2:768`. One number
  cannot serve both (bag-of-tokens puts same-domain text at ~0.2–0.4, a real
  embedder at ~0.7–0.9).
- **Two signals**: **recurrence** (stable period over ≥3 occurrences) and
  **reformulation** (≥3 episodes at cost > 1.5× baseline), always relative to
  the per-user baseline, never absolute.
- **Evidence-gated, not eager**: a weak cluster yields no candidate; a cold
  user (< 14 days / < 20 episodes) gets none and logs `detector_observing`.
- **Result (*legacy demo*)**: on the templated source the detector finds three
  distinct agents (`weekly_recap`, `standup_digest`, `incident_triage`), each
  with its own centroid, probes, fingerprint and cost. **On realistic fixtures
  this clean result does not reproduce**: see the status block.
