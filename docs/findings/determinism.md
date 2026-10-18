## 7. The embedding model is deterministic; the generation model is not


```
frozen cache vs AI Studio gemini-embedding-2   : 1.000000
norm over 200 cache vectors : min 1.000000  max 1.000000  mean 1.000000
```

Re embedding the same 200 texts a month later reproduces the committed cache
exactly. That is what makes `CachedEmbedder` a legitimate stand in for the live
substrate rather than an approximation of it.

The **generation** model is a different story: facets generated at T=0 vary
between runs, which is why every facet figure above is measured on one frozen
generation and says so.

**Measured, not asserted.** The cross-user bench was run **five** times over the
same 46 clusters, same corpus, same protocol. Recall at a matched false-positive
rate, facet-redacted. Run 4 is the generation the committed
`dashboard_level_2/data/crossuser_view.json` carries and the board renders; run 5
was drawn afterwards as a check and did not replace it:

| budget | run 1 | run 2 | run 3 | run 4 | run 5 | spread |
|---|---:|---:|---:|---:|---:|---:|
| 10.1% FP | 75.0 | 76.4 | 71.4 | **69.3** | 74.3 | 7.1 points |
| 1% FP | 32.1 | 27.9 | 18.6 | **23.6** | 30.0 | **13.5 points** |
| the text baseline, same runs | 90.7 | 90.7 | 90.7 | **90.7** | 90.7 | identical to the decimal |

Run 5 landed inside the range the first four had already drawn at both budgets,
which is the useful thing about it: five draws have not widened the spread, so
the 7.1 and 13.5 are starting to look like the size of the effect rather than an
artefact of too few samples. The text baseline reproduced to the decimal a fifth
time.

**The spread depends on the error budget chosen, and that is not a defect in
itself.** It is 7.1 points at 10.1% false positives and 13.5 at 1%: a property of
the operating point, read at the budget whoever deploys the layer sets. What it
does require is that a deployment freeze its facets once and reuse them, so a
lifecycle decision is never re-rolled by a new draw - which the engine does by
construction, since a facet is generated at the agent's birth and never
regenerated (`docs/CAPABILITIES.md` §12).

Pinning key: `(2026-09-02, eca74ca+wt, google:gemini-embedding-2:768, n/a)` for
the determinism block; `(2026-09-08, f39c631+wt,
bigquery:gemini-embedding-001:768, gemini-flash @ T=0)` for the three runs.

```bash
uv run python examples/bigquery/space_identity.py          # the determinism block
uv run python examples/bigquery/facet_crossuser_bench.py   # one run of the three; BILLS
```

---
