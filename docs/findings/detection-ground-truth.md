## 1. Detection against external ground truth


Stack Overflow moderators close a question as a duplicate of another. That pairs
two texts by a human judgment the CLE never sees. Feed both halves through the
detector and ask whether they land in the same cluster.

```
137 episodes, 60 clusters detected
components with two or more members : 48
members landing in the SAME cluster : 32 / 48   (67%)
```

**67% against roughly 2% at random** (60 clusters). A third fails.

Pinned by `tests/unit/test_real_state_regression.py`, which recomputes both
numbers from the committed artifacts, so neither can drift without the suite
going red.

The same run, seen from the other end:

```
capture_rate 1.000    false_trigger_rate 0.580
```

**These two numbers describe one thing.** 67% is the share of attested intents
the detector groups; 0.580 is the share of what a resulting trigger fires on that
was not the intent. Publishing the first without the second would be publishing
half a measurement. A detector that grouped everything into one cluster would
score 100% on the first and 1.0 on the second.

Pinning key: `(2026-09-02, eca74ca+wt, google:gemini-embedding-2:768 @ 0.775,
stub-model-1)`.

## 0.580 was the measurement path, not the detector

`(2026-10-17, 2a997be+wt, google:gemini-embedding-2:768 @ 0.775, stub-model-1)`

```
capture_rate 1.000    false_trigger_rate 0.000      (three largest clusters: 0.000, 0.000, 0.000)
```

Replay routed every opener against `config.cluster_similarity_threshold` - a
**0.6 applied in every space** - while the clustering half of the same build
used the calibrated 0.775. In this space 0.6 sits BELOW the cross-intent median
of 0.61, so 76 of 131 out-of-cluster episodes cleared it: that is exactly
76/131 = 0.580. At the space's own bar the same trigger fires on 0 of 131.

The old number is kept above because it is what the engine measured while it
routed that way, and because the reading it produced - "the detector fires on
everything" - was repeated for months. The defect was one line
(`cle/build/replay.py`), it is now pinned by
`tests/unit/test_replay_routing_bar.py`, and it was invisible to the whole
offline suite because `stub:hashed64` is calibrated at 0.6, the very value the
unscoped code used.

Measured the same day in a second space, EmbeddingGemma-300m run locally
(`onnx:embeddinggemma-300m-fp16:query:768 @ 0.46`): **40/48 (83%)** of attested
intents grouped, `capture_rate` 1.000, `false_trigger_rate` 0.000 / 0.000 /
0.023 on its three largest clusters. Two spaces, two partitions (42 clusters
against 60), and neither reading is a ranking: see `local-space-onnx.md`.

```bash
uv run python examples/bigquery/prepare_states.py && uv run python examples/bigquery/run_state.py stackoverflow
```

---
