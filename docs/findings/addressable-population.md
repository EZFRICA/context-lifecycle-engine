## 2. Addressable population


The CLE needs a user who has repeated themselves. Most have not.

```
WildChat users with enough usage (>=40 turns AND >=30 days) : 0.34%
of those, discarded by the coarse-timestamp guard           : 29/40
remaining                                                   : ~0.08% of the corpus
```

The timestamp guard does what it was built to do: those users carry one
timestamp per conversation rather than per turn, so silence-based episode
segmentation has nothing to segment.

**This is not a defect.** The engine refuses to manufacture an agent for someone
who has not repeated anything. It addresses intensive users, and 0.08% of a
corpus of a million people is still a large population. The figure binds level 2
to scale: a population report needs a corpus where 0.08% is a meaningful count.

Pinning key: `(2026-09-01, eca74ca+wt, n/a, n/a)` for the 0.34%;
`(2026-09-02, eca74ca+wt, google:gemini-embedding-2:768 @ 0.775, stub-model-1)`
for the 29/40, on a 40 user cohort.

```bash
uv run python examples/bigquery/wildchat_density.py
uv run python examples/bigquery/run_state.py wildchat
```

---
