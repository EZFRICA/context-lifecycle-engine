## 5. Corpus C, WildChat

Not public data. `allenai/WildChat-4.8M` is gated on Hugging Face: accept its
terms, then `huggingface-cli login`. It is **real user prompts, consented for
research**. Treat it accordingly.

```bash
uv run python examples/bigquery/load_wildchat.py         # streams from HF into BigQuery
uv run python examples/bigquery/extract_cohort.py
uv run python examples/bigquery/wildchat_density.py
```

`examples/bigquery/data/` and `examples/bigquery/states/` are gitignored in full,
and they must stay that way: the `episodes` and `text` columns hold raw prompts,
not summaries. Do not move a dump out of those directories.
