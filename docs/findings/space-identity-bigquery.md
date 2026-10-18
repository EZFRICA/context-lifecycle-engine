## 9. BigQuery and the engine finally share one space

`(2026-10-18, 2a997be+wt, google:gemini-embedding-2:768 against
bigquery:gemini-embedding-2:768, n/a)`

```
BigQuery raw norms          min 1.000000   max 1.000001
cosine, same 20 texts       min 1.000000   median 1.000000   max 1.000000
identical to 1e-6           20/20
```

Every corpus figure in this file is labelled `bigquery:gemini-embedding-001:768`
for one reason: BigQuery could not host the model the engine runs on, so cosine
between the bench space and the engine space was **0.040084** - different models,
not two views of one. BigQuery made `gemini-embedding-2` generally available on
2026-10-05, and the measurement above is what that changes: a remote model on
the new endpoint returns, for the same texts, the vectors the engine's own cache
holds.

Two consequences, and only two:

- **New benches can run in the engine's space.** The disclosed gap that
  conditions every figure here is closeable from now on.
- **The published figures do not move.** They were measured in
  `gemini-embedding-001` and stay labelled that way; re-running produces a new
  column beside them, never an edit (`cle-measurement-discipline`).

## The norms, measured side by side

Both models, the same 20 texts, the same surface, one run each:

| remote model | raw norms from `ML.GENERATE_EMBEDDING` | cosine against the engine's cache |
|---|---|---|
| `emb_gemini_embedding_2` | **1.000000 to 1.000001** | median **1.000000**, 20/20 identical to 1e-6 |
| `emb_gemini_embedding_001` | **0.582974 to 0.599283** | median **0.040290**, 0/20 |

The second row is why `assert_unit_norm` exists. `cosine` here is a raw dot
product, so a 0.583-norm vector compared **with itself** returns **0.3399**, not
1.0 - a perfect match read as a weak one, under every threshold in the system.
The guard refuses such a vector at the boundary rather than letting it produce
plausible numbers from an unusable geometry.

The 0.040290 median also corroborates the published 0.040084: these are two
different models, which is what the disclosed gap always said.

```bash
uv run python examples/bigquery/space_identity_2.py
uv run python examples/bigquery/space_identity_2.py --model emb_gemini_embedding_001
```
