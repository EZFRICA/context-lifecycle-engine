# CLE Findings on Real Data

What the engine does when it is pointed at corpora nobody generated for it.
Everything in `docs/METRICS.md` is measured on fixtures; everything here is
measured on Stack Overflow (public) or WildChat (research-consented prompts).

**Every number below carries its pinning key and the command that produced it.**
A number without its command does not belong in this file.

Pinning key format: `(date, commit, embedder_id, model_id)`.

`eca74ca+wt` names the tree a measurement ran on: commit `eca74ca` plus the
working tree that became the change these docs ship with. **The commit to
reproduce against is the one that carries this file**, not a hash written
inside it: a hash written here is wrong the first time the history is rewritten,
and rewriting it before publishing is normal.

Two vector spaces appear throughout, and they are **not the same model**:

| space | surface | used for |
|---|---|---|
| `google:gemini-embedding-2:768` | AI Studio, or Vertex at `global` | the CLE itself |
| `bigquery:gemini-embedding-001:768` | Vertex, `ML.GENERATE_EMBEDDING` | the corpus benches |

`gemini-embedding-2` is not available as a BigQuery remote-model endpoint, so
no BENCH could run in the CLE's own space: every bench here goes through
`ML.GENERATE_EMBEDDING`. Cosine between the two spaces, same texts: **0.040084**.
Read every bench figure as conditioned on `gemini-embedding-001`.

> **This is narrower than it used to be stated.** Earlier passes wrote that the
> model is "AI Studio only". It is not: `gemini-embedding-2` is served by the
> Vertex API at location `global` (it 404s at `us-central1` and `europe-west1`),
> reachable with application-default credentials, and it returns the SAME
> vectors as AI Studio (cosine 1.000000 against the committed cache, n=3). What
> is unavailable is the BigQuery remote-model endpoint, which is a narrower
> thing than "Vertex". A bench in the CLE's own space is therefore possible; it
> just cannot be written as a BigQuery query.

---

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

```bash
python examples/bigquery/prepare_states.py && python examples/bigquery/run_state.py stackoverflow
```

---

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
python examples/bigquery/wildchat_density.py
python examples/bigquery/run_state.py wildchat
```

---

## 3. What the detector's floor actually is

The floor is not about how much a user writes.

| threshold | what it buys |
|---|---|
| ~6 occurrences of one intent | a first cluster forms |
| ~10 occurrences of one intent | recovery is reliable |

**Episode count predicts nothing.** A user with 200 episodes spread across 200
distinct intents produces no cluster; a user with 30 episodes across 3 intents
produces 3. The quantity that matters is occurrences per intent, which is
recurrence behaving as recurrence.

Pinning key: `(2026-08-30, eca74ca+wt, google:gemini-embedding-2:768 @ 0.775,
stub-model-1)`.

```bash
python examples/make_multiuser.py && python examples/density_probe.py
python examples/criterion_probe.py
```

---

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

```bash
python examples/bigquery/embed_pairs.py && python examples/bigquery/intent_bench.py
```

---

## 5. No dedicated vector storage is justified at this scale

Exhaustive `VECTOR_SEARCH` stays **under 3 s at one million vectors**. The knee
is not reached on latency; what grows is cost per query, for lack of
partitioning. The question left open when `WeaviateStore` was deleted has a
measured answer, and the answer is that the deletion cost nothing.

The BigQuery vector index itself is **not measured** (coverage 0% at end of
run). Stated as unmeasured, never estimated.

Related, and it is why BigQuery is not the state backend either: a point read of
a 15.4 Ko witness table takes a median **1 363 ms** and bills **10.5 Mo**.

Pinning key: `(2026-09-01, eca74ca+wt, bigquery:gemini-embedding-001:768, n/a)`.

```bash
python examples/bigquery/vector_search_bench.py
```

---

## 6. The cost of the facet boundary

A facet is a one sentence description of what an agent does, standing in for the
episodes it was born from. Summarising loses information. How much depends
entirely on what you measure it against.

| comparison | agreement |
|---|---|
| centroid cosine, the upper bound available | **99.3%** |
| strict facet contract | 12.0 points below |
| relaxed facet contract | 2.9 points below |

**Measured on intent components, not on question pairs.** Comparing whole
questions answers a different question and gives a much larger loss; the object
being summarised has to be the object the agent is born from.

The internal gaps between the three rows are the finding. The absolute level is
conditioned on `gemini-embedding-001` and it is unknown whether the same ordering
holds in the CLE's space, which would need the facet corpus re embedded through
AI Studio.

The centroid costs nothing to compute and is the upper bound measured here, so
nothing in the facet path currently earns its keep against it.

Pinning key: `(2026-09-02, eca74ca+wt, bigquery:gemini-embedding-001:768,
gemini-3.6-flash for facet generation)`.

```bash
python examples/bigquery/make_facets.py && python examples/bigquery/intent_bench.py
```

---

## 6b. Facets on the task level 2 actually does, and what they cost there

§6 measures facets on intent components. Level 2's task is different: read many
independent topologies and decide whether two of them carry the SAME recurring
intent. The negative is two strangers' unrelated intents, not two questions one
person asked a week apart — and the negative turns out to decide the answer.

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
two real users would. That inflation favours the text methods specifically — raw
text from one generator shares surface vocabulary, which a facet abstracts away.
On real users the gap should narrow, by an unmeasured amount.

Pinning key: `(2026-09-06, b9d9556+wt, bigquery:gemini-embedding-001:768,
gemini-2.5-flash for facet generation)`.

```bash
python examples/make_multiuser.py --users 12 --prefix ph12
python examples/bigquery/facet_crossuser_bench.py
```

---

## 6c. The ranking of methods depends on where the threshold sits

Three independent datasets in this project, one behaviour.

| dataset | free lexical vs the best model, at 10.1% FP | at 1% FP |
|---|---|---|
| Stack Overflow duplicate pairs | 11.7 points behind | **4.9 points ahead** |
| facets, within one user | 0.3 points ahead of the facet pipeline | 4.6 points ahead |
| intents, across users | 12.8 points behind facets | **22.8 points ahead** |

Same corpus, same pairs, same protocol in each row; only the error budget moves.
An aggregate rank metric hides this completely — AUC puts the embedding first in
every one of the three.

The consequence for level 2 is a design order, not a preference: **fix the error
budget first, then choose the method.** A method chosen at a loose budget and
deployed at a strict one is not a slightly worse choice, it is sometimes the
wrong one.

```bash
python examples/bigquery/model_bench.py          # row 1
python examples/bigquery/facet_scale_bench.py    # row 2
python examples/bigquery/facet_crossuser_bench.py  # row 3
```

---

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

Pinning key: `(2026-09-02, eca74ca+wt, google:gemini-embedding-2:768, n/a)`.

```bash
python examples/bigquery/space_identity.py
```

---

## The comparison this file does NOT make

**No embedding model has been benchmarked against the CLE's own.** Every bench
above runs on BigQuery, and `gemini-embedding-2` has no BigQuery remote-model
endpoint, so it cannot appear in a BigQuery bench at all. (It is reachable on
the Vertex API directly, which is what makes a bench in the CLE's space
possible in principle.) The models that can be
compared there (`text-embedding-005`, `text-multilingual-embedding-002`, MiniLM,
`gemini-embedding-001`) are compared against each other, never against the one
the engine runs on.

```
frozen cache vs gemini-embedding-2   : 1.000000
frozen cache vs gemini-embedding-001 : 0.040084
```

Reproduce the second line with:

```bash
python examples/bigquery/space_identity.py
```

which re-measures the comparison over 20 texts and reports the distribution
rather than a single number:

```
norme L2 BigQuery : min=0.572648 max=0.599283
cosinus(cache, BigQuery) : min=-0.010125 med=0.036984 max=0.083587
vecteurs identiques a 1e-6 : 0/20
```

0.040084 sits inside that distribution, so the headline figure is corroborated;
what the re-measurement adds is that **no vector matches at all** (0 of 20) and
that the BigQuery norms sit at 0.57 to 0.60, which is what `assert_unit_norm`
refuses.

The only model present on both surfaces is `gemini-embedding-001`, and it is not
the CLE's. Answering "is there a better embedder for this?" needs a bench that
does not go through BigQuery.

---

## What none of this proves

- Nothing here says an agent born this way is **useful**: grouping intents is
  not serving them, and the CLE tests triggers, never answers.
- 67% is one corpus, one moderator population, one language distribution, and
  every bench figure is conditioned on `gemini-embedding-001`.
- The false trigger rate of 0.580 is a **measured defect** left frozen, not a
  target that was met, and the facet path is a **pilot** integrated into nothing.
- **No ground truth exists for demotion.** Detection has an external check (a
  moderator closing one question as a duplicate of another is a judgment the
  detector never sees). Nothing plays that role for whether a demotion was
  correct, so lifecycle figures show the machinery running, not deciding well.
- **Level 2 does not exist.** Nothing here aggregates across more than one
  topology history. The closed vocabulary, the embedding key and the provenance
  fields are necessary-condition work, not aggregation: no figure here is a
  population figure.

See `docs/METRICS.md` for fixture era numbers, `docs/CAPABILITIES.md` for components.
