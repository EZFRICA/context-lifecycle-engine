## 6b-ter. Stack Overflow across authors: real users AND real labels


§6b measured on synthetic users; §6b-bis on real users without labels. Stack
Overflow has both, and this repository had the data all along without using it:
**662,401 duplicate closures link questions written by DIFFERENT authors.** A
moderator ruling that two strangers asked the same question is exactly level 2's
positive. `corpus_a_selfdup` kept only the 15,026 same-author pairs, because it
was built for the detector, which sees one user at a time.

Controls come from the same tags the positives use, by different authors, with no
duplicate link - so the bench measures *same intent* against *merely same
subject*. 3,000 pairs, 1,500 of them cross-author duplicates.

| method | @10.1% FP | @5% FP | @1% FP | AUC |
|---|---:|---:|---:|---:|
| title-jaccard | 38.0% | 28.4% | 14.2% | 0.6938 |
| title-cosine | **61.1%** | **51.7%** | **35.8%** | 0.8491 |
| facet-cosine | 54.3% | 42.7% | 24.3% | 0.8203 |
| facet-redacted | 54.8% | 41.1% | 24.2% | 0.8045 |

**This settles what §6b-bis left open.** WildChat showed facets surfacing 135
cross-user pairs above 0.7 against raw text's 19, and two readings fitted: facets
recover structure raw text cannot see, or facets over-merge. On real users with
real rulings, raw text beats facets at every budget. Surfacing more candidates
was not finding more matches.

Both labelled cross-user benches now agree on the ordering:

| corpus | users | text | facet, redacted | gap |
|---|---|---:|---:|---:|
| GDG, synthetic | 12, one generator | 90.7% | 69.3% | 21.4 |
| Stack Overflow | thousands of real authors | 61.1% | 54.8% | 6.3 |

Both rows are `bigquery:gemini-embedding-001:768`. Re-measured in the engine's
own space on 2026-10-18, the GDG gap falls to 5.7 points (§6b) and this one
widens to 7.5 - so the corpus is no longer what separates them.

The GDG facet figure is the generation the board renders; §7 gives the spread of
five generations around it.

The synthetic corpus overstated the gap, as its own caveat predicted. It did not
invert it.

## Re-run in the engine's own space, 2026-10-18

`(2026-10-18, 2a997be+wt, bigquery:gemini-embedding-2:768, facets frozen under
gen_gemini_flash)`. Same definition of a pair, same committed facets, 3,000
pairs drawn among the titles that already carry one.

| method | published `gemini-embedding-001` | `gemini-embedding-2` |
|---|---:|---:|
| title-jaccard | 38.0% | 38.1% |
| title-cosine | 61.1% | **62.7%** |
| facet-cosine | 54.3% | 56.1% |
| facet-redacted | 54.8% | 55.2% |
| **text over redacted facet** | **6.3** | **7.5** |

**The lexical baseline is the control that validates the redraw.** Jaccard uses
no embedding at all, so its 38.1% against the published 38.0% says this sample
behaves like the published one - which matters, because the original pair list
was never persisted and the query carries no `ORDER BY`, so an identical draw
was not available.

The ordering is unchanged and the gap widens slightly: in the space the engine
actually runs on, raw text beats the redacted facet by 7.5 points rather than
6.3. Nothing here reverses §6b-ter; it confirms it where it matters most.

```bash
uv run python examples/bigquery/so_rerun_space.py
```

**No threshold inversion on this corpus**, and it is the first here without one:
free word overlap is last at 10.1%, at 5% and at 1%. Two questions the same person
asked a week apart are often near-restatements, which is what made lexical overlap
competitive in §1. Two strangers asking the same thing rarely reuse each other's
words - 38.0% against 62.9% on the synthetic corpus.

The absolute level is lower than §6b throughout (61.1% against 90.7%) because the
control is harder: same-tag pairs by different authors, not a derangement.

Pinning key: `(2026-09-10, output committed in 25c6e0c,
bigquery:gemini-embedding-001:768, the gen_gemini_flash remote model for facet
generation)`. The figures are the ones `dashboard_level_2/data/so_view.json`
carries.

```bash
uv run python examples/bigquery/facet_crossuser_so_bench.py
```

---
