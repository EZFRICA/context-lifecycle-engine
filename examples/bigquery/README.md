# Corpus measurement scripts

These are **not part of the engine**. They are the commands that produced the
figures in `docs/FINDINGS.md`, kept so those figures can be reproduced rather
than believed. Nothing here is imported by `cle/`, `dashboard/` or the test
suite.

```bash
uv pip install -e ".[measure]"
```

**Setting up a project to run these is `docs/BIGQUERY.md`**: dataset, EU
connection, the Vertex IAM grant the connection needs, the remote models, and
where each corpus comes from.

Configuration comes from `.env`, with **no defaults**. `bqconfig.py` raises
rather than guessing a project, dataset, region or connection, because a script
that defaults to somebody's live infrastructure is a script that runs somewhere
unexpected.

```
CLE_BQ_PROJECT=    CLE_BQ_DATASET=    CLE_BQ_REGION=    CLE_BQ_CONNECTION=
```

## Cost and privacy

**These scripts bill.** BigQuery scans and `ML.GENERATE_EMBEDDING` calls both
cost money; the measured figures are in each script's header. Read the header
before running one.

`examples/bigquery/data/` and `examples/bigquery/states/` are **gitignored in
full**. They hold real WildChat prompts: the `episodes` column of the facet files
and the `text` column of the cohort files are raw user text, not summaries. Do
not move anything out of those directories, including a `read_data.py --dump`.

## What each script measured

| script | what it measures |
|---|---|
| `bqconfig.py` | nothing; the configuration boundary |
| `load_wildchat.py` | loads WildChat-4.8M in the shape the detector consumes |
| `extract_cohort.py` | the WildChat cohort's text |
| `wildchat_density.py` | true per-user structure across all 86 shards |
| `extract_corpus_b.py` | the matched control for self-duplicate pairs |
| `extract_corpus_c.py` | 90-day recurrence windows |
| `build_zero_overlap.py` | the pairs a lexical baseline cannot see |
| `embed_pairs.py` | cosine over every corpus A and B pair |
| `embed_corpus_c.py` | corpus C titles, embedded once |
| `kmeans_oracle.py` | k-means as an ORACLE, never as the detector |
| `space_identity.py` | is BigQuery's embedding space the CLE's? **No** |
| `vector_search_bench.py` | `VECTOR_SEARCH` cost and latency |
| `model_bench.py` | embedding models on the existing bench |
| `make_facets.py` | facet generation from real clusters, **pilot** |
| `facet_groundtruth.py` | do facets preserve a moderator's judgment? |
| `intent_bench.py` | the intent-level bench, and why the previous one was the wrong object |
| `prepare_states.py` | the two real corpora, in CLI-consumable shape |
| `run_state.py` | drives a real corpus through the CLI into its own state dir |
| `read_data.py` | reads the parquet artifacts as text; they are not human readable |

## Reading the results

Parquet is columnar binary. `read_data.py` turns it into something openable:

```bash
python examples/bigquery/read_data.py                      # the catalogue
python examples/bigquery/read_data.py facets_pilot         # schema + first rows
python examples/bigquery/read_data.py facets_pilot --dump  # full text, to a file
```

## Two things these scripts settled

**BigQuery is not a state backend.** A point read of a 15.4 Ko witness table
takes a median 1 363 ms and bills 10.5 Mo. Measured before any backend was
designed, which is why none was.

**The bench never contained the CLE's model.** `gemini-embedding-2` is AI Studio
only; `ML.GENERATE_EMBEDDING` runs `gemini-embedding-001` on Vertex. Cosine
between the two spaces on the same texts is 0.040084. Every figure produced here
is conditioned on `gemini-embedding-001`, and `docs/FINDINGS.md` says so beside
each one.
