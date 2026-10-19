## Measured reality - do not re-derive these the hard way
Recorded so no one repeats an assumption the measurements already refuted.
Fixture numbers and their provenance: docs/METRICS.md. Numbers measured on real
corpora, each with its pinning key and reproduction command: docs/FINDINGS.md.
- **Detection was only clean because the fixtures were templated.** On
  realistic phrasing the v1 embedder fragments every intent into
  near-singletons; holdout discovery falls to 0.
- **A real embedder is not a drop-in.** At the stub's threshold it
  over-merges (2 clusters, `false_trigger` 0.632). Recalibrated it beats v1
  but still recovers a minority of planted intents.
- **Cosine is the wrong operator for contradiction.** It measures topical
  relatedness: planted OPPOSING directives score 0.62–0.86 *because they are
  about the same thing*. The four-type taxonomy is therefore inert outside
  `stub:hashed64`, and no threshold rescues it - it needs a signed/entailment
  operator, which is not in v1 scope.
- **Candidate counts never stand bare.** Report them with purity against the
  planted intents (GENUINE / FRAGMENT / SPURIOUS); a bare count hides
  noise agglomerates.
- **The floor is OCCURRENCES PER INTENT, not episode density.** ~6 for a first
  cluster, ~10 for reliable recovery. Episode count predicts nothing: 200
  episodes across 200 distinct intents produce no cluster. R24 framed this as
  density and was wrong.
- **Recovery and false-trigger are one measurement seen from two ends.** On
  Stack Overflow moderator ground truth the detector groups 26/39 components
  (67%, against ~2% at random) at `false_trigger_rate` 0.580. Publishing either
  alone publishes half a measurement: grouping everything into one cluster
  scores 100% on the first and 1.0 on the second.
- **The signal is caudal.** Floor 0.464 on raw text, 0.519 to 0.561 on facets;
  factor 1.08 on the mean but 12.9 on the share above 0.7. Anything reading mean
  similarity sees ~0.55 everywhere and concludes nothing.
