## Three data sources, three roles

Evaluating a detector on data generated with that detector's own geometry is a
consistency check, not a discovery test. So:

| Source | Role | Status |
|---|---|---|
| **ground truth** (`make_gdg_fixture.py`) | **recovery**: planted patterns must come back | realistic (era B/C) |
| **adversarial** (`make_fixture.py`) | **rejection**: a bridge fires, traps do not | **still templated** (era A) |
| **holdout** (`make_holdout.py`) | **discovery**: unplanted patterns emerge | realistic; imports **nothing** from `cle` |

The holdout is the only one authored without knowledge of the embedder geometry,
the cosine threshold, or any centroid. That is what makes it the confirmation
point above.

**Anti-templating guard** (`test_fixture_realism.py`): asserts **data**
properties grouped by planted intent (≥8 distinct openers per recurring intent,
no sentence >15% of messages, timing not single-valued), so a fixture regressing
to templated text fails the suite instead of being found three runs later.

---
