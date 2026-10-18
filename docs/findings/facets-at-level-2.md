## 6b. Facets on the task level 2 actually does, and what they cost there


§6 measures facets on intent components. Level 2's task is different: read many
independent topologies and decide whether two of them carry the SAME recurring
intent. The negative is two strangers' unrelated intents, not two questions one
person asked a week apart - and the negative turns out to decide the answer.

Ground truth by construction: `make_multiuser.py` partitions the GDG corpus into
12 synthetic users and every message carries its intent in `thread_id`. A
positive is two DIFFERENT users' clusters of the same planted intent. 46
clusters, 966 cross-user pairs, 140 positive. Nothing was labelled by hand.

| method | @10.1% FP | @5% FP | @1% FP | AUC |
|---|---:|---:|---:|---:|
| text-jaccard, free | 62.9% | 59.3% | **52.1%** | 0.8308 |
| text-cosine | **90.7%** | **81.4%** | 61.4% | 0.9645 |
| facet-cosine | 75.7% | 62.1% | 29.3% | 0.9230 |
| facet-redacted | 75.0% | 62.1% | 32.1% | 0.9271 |

**Raw text beats facets on this task** by 15.0 points at a 10.1% budget and 32.1
at 1%. The 15 points are not a defect to engineer away: they are the price of the
property the facet contract exists to buy, which is never storing user text at
all. `text-cosine` wins by embedding the raw episodes, so a population layer
built on it reads what people wrote.

**Mechanical redaction is free here.** 75.0% against 75.7%, better at the strict
budget, and the leak goes from 0.11 proper nouns per facet to 0.00. On the
within-user task the same redaction cost 2.3 points and finished last: there the
redacted token was the only thing separating two of one person's questions;
across users it is incidental. If facets are used, redact.

**UPPER BOUND, NOT AN ESTIMATE, and it is not uniform.** `make_multiuser.py`
states the bound: one generator, so two users sharing an intent sit closer than
two real users would. That inflation favours the text methods specifically - raw
text from one generator shares surface vocabulary, which a facet abstracts away.
On real users the gap should narrow, by an unmeasured amount.

Pinning key: `(2026-09-06, b9d9556+wt, bigquery:gemini-embedding-001:768,
gemini-2.5-flash for facet generation)`.

## Re-run in the engine's own space, 2026-10-18

`(2026-10-18, 2a997be+wt, bigquery:gemini-embedding-2:768, the SAME facets read
back from `r26_cluster_facets`)`. Same 46 clusters, same 966 pairs, nothing
regenerated; only the embedding model differs.

| method | published `gemini-embedding-001` | `gemini-embedding-2` |
|---|---:|---:|
| text-jaccard, free | 62.9% | 62.9% |
| text-cosine | **90.7%** | **80.0%** |
| facet-cosine | 75.7% | 75.0% |
| facet-redacted | 75.0% | 74.3% |
| **text over redacted facet** | **15.0** | **5.7** |

**`text-jaccard` is identical to the decimal** - 62.9 / 59.3 / 52.1, AUC 0.8308
in both - and it uses no embedding at all. That is the control saying the
clusters and the pairs are the published ones, so the rest of the column is a
space effect and nothing else.

**The price of the facet boundary on this task is a third of what was
published.** Raw text keeps winning, but by 5.7 points instead of 15.0: moving
to the engine's own space costs `text-cosine` 10.7 points while the facet rows
barely move. At the 1% budget the facets actually improve (29.3% to 38.6%) while
text falls (61.4% to 56.4%).

**It does not reverse the finding, and it does not soften the caveat.** The
corpus is still 12 synthetic users from one generator, still an upper bound that
favours the text methods; what changed is the size of a gap that was read as
"the price of never storing user text". In the space the engine actually runs
on, that price is smaller than the figure this section has carried.

```bash
uv run python examples/bigquery/facet_crossuser_bench.py --model emb_gemini_embedding_2
```

```bash
uv run python examples/make_multiuser.py --users 12 --prefix ph12
uv run python examples/bigquery/facet_crossuser_bench.py
```

---
