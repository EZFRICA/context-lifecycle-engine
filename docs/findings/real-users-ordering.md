## 6b-bis. On real users, the ordering reverses


§6b measured facets against raw text on 12 SYNTHETIC users and found raw text 15
points ahead. That corpus states its own bound - one generator, so two users
sharing an intent sit closer than two real users would, and the inflation
favours the text methods specifically.

Repeating the comparison on **40 real WildChat users** (130 clusters, 8,128
cross-user pairs, facets generated once by `make_facets.py`) inverts it:

| method | median | p99 | pairs ≥ 0.7 | ≥ 0.8 |
|---|---:|---:|---:|---:|
| raw episodes, embedded | 0.520 | 0.660 | **19** | 3 |
| raw episodes, free word overlap | 0.023 | 0.111 | **0** | 0 |
| facet, embedded | 0.563 | 0.716 | **135** | 5 |
| facet after mechanical redaction | 0.563 | 0.716 | **135** | 5 |

**Facets surface 7x more candidate cross-user matches than raw text.** The
synthetic bench predicted the direction and understated the size: 40 strangers do
not share a generator, so their raw-text similarity is dominated by style and
register while the facet describes the task underneath.

**This is not recall, and the distinction is the point.** Nobody has labelled
which two real users share an intent, so 135 pairs above 0.7 is 135 candidates,
not 135 correct matches. Facets are also the method that collapses two
neighbouring tasks into one generic sentence, and over-merging produces this
number too. The two readings are indistinguishable without cross-user ground
truth on real users, which does not exist in this repository.

**Free lexical overlap is not in the race here.** Median 0.023, and not one pair
of 8,128 reaches 0.7 - against a Stack Overflow bench where the same baseline beat
every embedding at a 1% budget. It grips when two texts say the same narrow thing
in the same words; across 40 strangers writing in several languages, there is
nothing to grip.

**Redaction is free on this corpus for a different reason than on the last one.**
`facet` and `facet-redacted` agree to four decimals: real WildChat facets carry
almost no proper nouns, so the mechanical guard removes nothing. It still earns
its place - the property is that it CANNOT leak, not that it usually does not.

Pinning key: `(2026-09-06, 7231fec+wt, bigquery:gemini-embedding-001:768, facets
generated earlier by make_facets.py)`.

## The same pairs in two more spaces, 2026-10-17

Same 130 clusters, same 8,128 cross-user pairs, same frozen facets; only the
space changes. **A fixed 0.7 bar does not travel** - the repository's own rule -
so both readings are given: the published one at its own bar, and a
budget-matched one that is space-independent.

| | published `gemini-embedding-001` | `onnx:embeddinggemma-300m-fp16:query` | `gemini-embedding-2` |
|---|---:|---:|---:|
| median, raw episodes | 0.520 | 0.177 | 0.509 |
| median, facet | 0.563 | 0.225 | 0.562 |
| pairs ≥ 0.7, raw / facet | 19 / 135 | 2 / 4 | 6 / 163 |
| facet over raw, **at a 0.1% budget** | not computed | **7.0x** | **33.4x** |
| free word overlap ≥ the same bar | 0 | 0 | 0 |

**The direction is robust, the amplification is not.** In all three spaces the
facet surfaces several times more candidate cross-user pairs than raw episodes,
and lexical overlap surfaces none at any bar. How MANY times more ranges from 7
to 33 depending on the space, so the published "7x more candidates" is a fact
about one space, not about facets.

`gemini-embedding-2` sits where `gemini-embedding-001` sat (medians 0.509/0.562
against 0.520/0.563) - two versions of one model family at a similar scale -
while the local Gemma space sits far lower (0.177/0.225). That is why the counts
collapse there and why only the budget-matched row means anything across the
three.

**None of this becomes recall.** More candidates is still not more matches:
over-merging produces the same number, and no label on real users exists to tell
the two apart. The 33x figure makes that caveat more urgent, not less.

```bash
uv run python examples/space_rerun_bench.py --figure wildchat-spread --space onnx
CLE_VERTEX_PROJECT=<project> uv run python examples/space_rerun_bench.py \
    --figure wildchat-spread --space real
```

```bash
uv run python dashboard_level_2/export_real.py
```

---
