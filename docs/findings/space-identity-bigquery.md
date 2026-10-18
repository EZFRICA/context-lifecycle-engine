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

Also worth recording: `ML.GENERATE_EMBEDDING` on this endpoint returns **unit
vectors**. On `gemini-embedding-001` it returned norms of 0.57 to 0.60, which is
what `assert_unit_norm` exists to refuse, and what made a BigQuery vector
unusable in `cosine` without an explicit normalisation at the boundary.

```bash
uv run python examples/bigquery/space_identity_2.py
```
