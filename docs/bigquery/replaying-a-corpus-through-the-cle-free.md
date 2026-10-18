## 7. Replaying a corpus through the CLE, free

Once `prepare_states.py` has written the histories and the vector cache exists,
this needs neither BigQuery nor an API key:

```bash
uv run python examples/bigquery/run_state.py stackoverflow
uv run python examples/bigquery/run_state.py wildchat
```

It reads `examples/bigquery/data/vectors.corpus_states.json` through
`$CLE_VECTOR_CACHE`, builds at `--model-id stub-model-1`, and refuses to run on
`.cle`. Reproduces the detection figures at zero cost.

---
