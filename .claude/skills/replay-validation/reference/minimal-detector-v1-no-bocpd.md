## Minimal detector (v1 - no BOCPD)
- Episodes: split on silence > threshold or explicit markers ("thanks",
  new-thread). Closure classification: `success` (explicit marker / no
  return), `reformulated` (no marker, returned to cluster in window),
  `abandoned` (no marker, no return, cost > 1.5× baseline) - abandoned
  episodes are EXCLUDED from cost baselines (the anti-Goodhart guard from
  part 7).
- Clusters: embed the episode opener behind the `Embedder` Protocol,
  incremental clustering; per cluster keep frequency, mean cost, trend,
  temporal distribution.
- **The similarity threshold is a property of the VECTOR SPACE, never a global
  constant.** It travels with `embedder_id` (`CLUSTER_THRESHOLD_BY_EMBEDDER`):
  0.6 for `stub:hashed64`, 0.775 for `google:gemini-embedding-2:768`.
  Bag-of-tokens puts same-domain text at ~0.2–0.4, a real sentence embedder at
  ~0.7–0.9 - one number cannot serve both. An unmapped embedder falls back to
  the config value and must be swept before it is trusted.
- Signals: reformulation = ≥3 in-window episodes at cost >1.5× user baseline;
  recurrence = stable period over ≥3 occurrences. Thresholds are config with
  article defaults; ALWAYS relative to the per-user baseline, never absolute.
- Per-user baseline: median iterations across the user's clusters, recomputed
  daily, excluding abandoned closures.
