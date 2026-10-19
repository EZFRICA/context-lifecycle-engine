## 3. Remote models

The benches address a model as `emb_<endpoint>` inside your dataset. Create the
ones you intend to use:

```sql
CREATE OR REPLACE MODEL `your-project.cle.emb_gemini_embedding_001`
REMOTE WITH CONNECTION `your-project.eu.vertex_eu`
OPTIONS (ENDPOINT = 'gemini-embedding-001');
```

`model_bench.py` compares several, so repeat for `text_embedding_005` and
`text_multilingual_embedding_002` if you want the comparison.

> **`gemini-embedding-2` became available here on 2026-10-05**, and that changes
> what the published bench figures are conditioned on. The BigQuery release notes
> of that date add `gemini-embedding-2` to `AI.EMBED`, `AI.SIMILARITY` and
> `AI.GENERATE_EMBEDDING` as generally available; it had been
> `gemini-embedding-2-preview` since 2026-04-22, and `gemini-embedding-001` has
> been GA since 2026-03-06. Until then this document said the model had no
> BigQuery endpoint at all, which was true when written and is why **every bench
> figure in `docs/FINDINGS.md` is labelled `bigquery:gemini-embedding-001:768`**:
> the benches could not run in the engine's own space, and cosine between the two
> MODELS on the same texts is 0.040084, so the gap was disclosed rather than
> crossed.
>
> **Nothing here has been re-measured in the new endpoint yet.** A figure is
> conditioned on the space that produced it, so the published ones stay as they
> are, labelled as they are; re-running a bench against
> `ENDPOINT = 'gemini-embedding-2'` produces NEW figures in a new space, beside
> the old ones, never a correction of them. What that would settle is worth
> stating plainly: whether the engine's space and the bench space can finally be
> the same one, which would remove the one disclosed gap that runs through every
> corpus figure in this repository.
