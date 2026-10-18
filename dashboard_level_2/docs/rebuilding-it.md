## Rebuilding it

The exports and the discovery bill BigQuery; the build does not.

```bash
uv run python examples/bigquery/facet_crossuser_so_bench.py   # -> data/so_view.json
uv run python dashboard_level_2/export_real.py                # -> data/real_view.json
uv run python dashboard_level_2/export_view.py                # -> data/crossuser_view.json
uv run python dashboard_level_2/discover_intents.py           # groups, names, families
uv run python dashboard_level_2/build.py                      # data/ -> index.html
```

Any missing export is simply absent from the selector; the board never pretends
to have a corpus it does not.

`export_real.py` reads gitignored WildChat material. Without it the board falls
back to the synthetic view alone rather than pretending it has real data.

`export_view.py` needs the BigQuery setup in `docs/BIGQUERY.md`, plus the remote
model `gen_gemini_flash` for facet generation. `build.py` needs nothing but the
committed `data/` files, so the board can be rebuilt offline after a style change.
