## What got WORSE

1. **Contradiction detection: from partial to none.** The whole four-type
   taxonomy is inert under a semantic embedder.
2. **`false_trigger` at the unchanged threshold: 0.061 → 0.632** (10×; events
   intent, ideal centroid).
3. **Over-merging replaces over-fragmenting**: and hides better, because
   `capture` *rises* (0.50 → 0.81) while the trigger steals most out-of-cluster
   traffic.
4. **Holdout 0 → 1 at 0.6 is spuriously non-zero** (a single noise-dominated
   mega-cluster, purity 14/41), a number that looks like progress and is not.
5. **`venue_policy`'s over-flag "fix" is illusory.**
6. **A new calibration coupling**: the threshold is now embedder-specific and
   must be versioned with `embedder_id`, or centroids and thresholds silently
   disagree.

---
