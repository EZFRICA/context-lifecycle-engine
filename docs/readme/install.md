## Install

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"                 # engine + test suite
uv pip install -e ".[dev,dashboard]"       # + the FastAPI dashboard
uv pip install -e ".[dev,measure]"         # + the corpus measurement scripts
```

`cle dashboard` imports uvicorn; the reproduction commands in
`docs/FINDINGS.md` need pandas and the BigQuery client (`docs/BIGQUERY.md`).
