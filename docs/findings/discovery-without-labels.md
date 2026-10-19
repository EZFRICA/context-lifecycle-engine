## 6d. Discovering intents without labels: what a calibrated threshold does to real corpora


Every section above measures against known positives. This one has none: it runs
Clio's stages 2–4 over corpora where nobody has said which users share an intent,
which is the situation a population layer is actually in.

The threshold is the one calibrated on the only corpus with planted intents -
0.78, chosen by sweep at purity 76% / completeness 80% / F 0.782. Applied
unchanged to real corpora it does this:

| corpus | users | groups | singletons | named | families @0.74 |
|---|---:|---:|---:|---:|---:|
| Stack Overflow, cross-author | real | 367 | **345** | 6 | 310 |
| WildChat | 40 real | 116 | **105** | **0** | 71 |
| GDG, synthetic, labelled | 12 | 9 | 2 | 4 | 1 |

**Three things this says.**

**1. The share of singletons is a property of the corpus at a threshold, not a
verdict on the system.** At 0.78, 94.0% of Stack Overflow groups and 90.5% of
WildChat groups are singletons. That is the 0.34%-of-users figure (§2) arriving
from the other end: most real cross-user clusters have no counterpart among
strangers. The threshold is a parameter (`cle population --threshold`, the
first argument of `discover_intents.py`), and another corpus or another value
gives another share. What these runs establish is that the stages run end to end
on real data, and that the floor and the screen do what they are for.

**2. The k-anonymity floor bites, visibly, on the corpus that most needed it.**
WildChat names **nothing**. Two of its groups were large enough to describe and
came from **two distinct people each**, so the floor suppressed both names. The
group keeps its id and its position on the plot; only the vocabulary is
withheld. This is BLUEPRINT §7c's *"a single global floor is insufficient, and
is known to be"* observed rather than predicted - and it is the floor working,
not failing.

**3. Clio's stage 4 buys much less than the corpora suggest.** 367 groups reduce
to 310 families (**15.5% fewer**) and 116 to 71 (**38.8% fewer**). The two
numbers are not the same story and neither is "almost nothing": WildChat's
reduction is real, Stack Overflow's is marginal. What both share is that the
reduction is bounded by singletons - a group of one has nothing to be grouped
with, and 94.0% of Stack Overflow groups and 90.5% of WildChat groups are
singletons. Stage 4 is doing what it can with what stage 2 left it. The
family threshold could not be calibrated against truth - no corpus here has a
labelled hierarchy - so it was chosen structurally, on the rule *reduce the count
without one family swallowing the corpus*:

| gap | threshold | SO families (largest) | WildChat families (largest) |
|---:|---:|---|---|
| 0.02 | 0.76 | 337 (16) | 83 (23) |
| **0.04** | **0.74** | **310 (31)** | **71 (33)** |
| 0.06 | 0.72 | 271 (51) | 45 (58) |
| 0.10 | 0.68 | 155 (74) | 10 (**106**) |

At 0.10 WildChat puts 106 of its 116 groups in **one** family. That is not a
hierarchy, it is a collapse, and it is why the chosen value is the conservative
end of the sweep rather than the one that reduces most.

**A non-measurement that looks like a result.** On WildChat the `facet` and
`facet-redacted` rows are identical to four decimals at every statistic -
median 0.5631, p99 0.7156, 135 pairs ≥ 0.7. Not a bug: mechanical redaction
changed **0 of 130** WildChat facets, so the two rows embed the same strings.
Read carelessly this says *redaction is free*; what it says is that this corpus
never exercised it. Redaction does move the number on both labelled corpora
(Stack Overflow 54.3 → 54.8, GDG 72.1 → 69.3, in opposite directions). Invariant
7 of the contract, arriving unannounced in a table.

**What this does not establish.** The naming step runs one frozen generation, and
generation is not reproducible run to run (§7 below), so the six Stack Overflow
names and the four GDG names are one draw, not a stable vocabulary. Purity is
computable only on GDG (35/46, 76%) because it is the only corpus with planted
intents; the two real corpora have no accuracy figure here at all, and inventing
one is the failure this file exists to avoid.

`discover_intents.py` runs the engine's `cle.population` stages (grouping,
floor, screen, hierarchy); only the embedding and the namer run on BigQuery. Run
through them, every figure in the table above and the GDG purity reproduced.

Pinning key: `(2026-09-10, level2-facet-grouping-bench+wt,
bigquery:gemini-embedding-001:768, threshold 0.78 / family 0.74)`.

```bash
uv run python dashboard_level_2/discover_intents.py                  # all three views
uv run python dashboard_level_2/discover_intents.py 0.78 crossuser_view   # one view
```

---
