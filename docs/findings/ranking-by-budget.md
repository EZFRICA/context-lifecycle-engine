## 6c. The ranking of methods depends on where the threshold sits


Three independent datasets in this project, one behaviour.

| dataset | free lexical vs the best model, at 10.1% FP | at 1% FP |
|---|---|---|
| Stack Overflow duplicate pairs | 11.7 points behind | **4.9 points ahead** |
| facets, within one user | 0.3 points ahead of the facet pipeline | 4.6 points ahead |
| intents, across users | 12.8 points behind facets | **22.8 points ahead** |

Same corpus, same pairs, same protocol in each row; only the error budget moves.
An aggregate rank metric hides this completely - AUC puts the embedding first in
every one of the three.

The consequence for level 2 is a design order, not a preference: **fix the error
budget first, then choose the method.** A method chosen at a loose budget and
deployed at a strict one is not a slightly worse choice, it is sometimes the
wrong one.

```bash
uv run python examples/bigquery/model_bench.py          # row 1
uv run python examples/bigquery/facet_scale_bench.py    # row 2
uv run python examples/bigquery/facet_crossuser_bench.py  # row 3
```

---
