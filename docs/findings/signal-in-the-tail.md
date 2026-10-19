## 4. The signal lives in the tail, never in the mean


Semantic cohesion inside a 90 day window against pairs more than a year apart:

```
mean cosine        0.5190  vs  0.4807     factor 1.08
share above 0.7      2.70%  vs  0.21%     factor 12.9
```

Floors, measured three times, on three objects:

| object | floor (mean cosine, unrelated pairs) |
|---|---|
| raw text | 0.464 |
| facets, relaxed contract | 0.519 |
| facets, strict contract | 0.561 |

**Summarising does not lower the floor, it raises it slightly**, because every
facet is one sentence in the same register describing a task.

Consequence for any population level aggregator: it must be a tail mechanism, a
high threshold or k nearest neighbours. **An aggregator reading mean similarity
would see ~0.55 everywhere and conclude nothing.**

Pinning key: `(2026-09-02, eca74ca+wt, bigquery:gemini-embedding-001:768, n/a)`.

## The same pairs in a local space, 2026-10-18

`(2026-10-18, 2a997be+wt, onnx:embeddinggemma-300m-fp16:query:768, n/a)` -
9,675 openers from 200 users, 257,179 same-user pairs within 90 days against
7,747 more than a year apart.

| | published `gemini-embedding-001` | `onnx:embeddinggemma-300m-fp16:query` |
|---|---:|---:|
| mean cosine, near / far | 0.5190 / 0.4807 | 0.3759 / 0.1911 |
| **factor on the mean** | **1.08** | **1.97** |
| share ≥ 0.7, near / far | 2.70% / 0.21% | 14.00% / 0.62% |
| factor on the tail, at a matched 0.21% budget | 12.9 | **37.5** |

**The tail still wins, but the mean is not useless everywhere.** The sentence
this section carried - "an aggregator reading mean similarity would see ~0.55
everywhere and conclude nothing" - is true of the space it was measured in,
where unrelated pairs already sit at 0.48. In a space whose unrelated baseline
is 0.19, the mean separates by a factor of 2. So the design consequence holds
for the reason it was given only in high-floor spaces; what holds everywhere is
that the TAIL separates several times better than the mean (12.9 then, 37.5
here).

A fixed 0.7 does not travel, which is why the last row is budget-matched: the
bar is placed where the far population leaves the same 0.21% above it that the
published far population did.

```bash
uv run python examples/space_rerun_bench.py --figure tail-vs-mean --space onnx
```

```bash
uv run python examples/bigquery/embed_pairs.py && uv run python examples/bigquery/intent_bench.py
```

---
