# CLE Metrics, Eras A and B

The superseded measurement eras, kept because the current numbers are only
legible against what they replaced.

* **Era A**: the legacy templated demo. Clean results that came from templated
  fixtures, not from the detector working.
* **Era B**: realistic data on the v1 bag of tokens embedder. Where era A's
  results fell apart.

Era C, the current one, is in `docs/METRICS.md`. Measurements on real corpora are
in `docs/FINDINGS.md`.

---


- [Era A, the legacy templated demo (`examples/full_loop.sh`)](metrics-eras/era-a-the-legacy-templated-demo-examples-full.md) - Produced by `make_fixture.py`, which has **not** been de-templated. These
- [Era B, realistic data, v1 embedder](metrics-eras/era-b-realistic-data-v1-embedder.md) - Fixtures: freeze-once, generated once and **committed** (determinism comes from
