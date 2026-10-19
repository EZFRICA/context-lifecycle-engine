## 6. Reading what comes back

Parquet is columnar binary:

```bash
uv run python examples/bigquery/read_data.py                      # the catalogue
uv run python examples/bigquery/read_data.py facets_pilot         # schema + first rows
uv run python examples/bigquery/read_data.py facets_pilot --dump  # full text, to a file
```
