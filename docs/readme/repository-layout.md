## Repository layout

```
cle/
  store/        objects, commits (SourceSpec, Image, TriggerSpec, evidence), backends
  detect/       episodes, clusters, embedders (+ provenance), signals, stability
  build/        resolver, replay, assembler, fingerprinter
  runtime/      container, mounts, metrics_volume
  lifecycle/    tags, engine (shadow), topology, revalidator, reasons (closed vocabulary)
  batch_guard.py  the three silent-failure guards
  logs.py       diagnostics to stderr; level and file from the environment
  cli/main.py   typer
dashboard/      backend/ (FastAPI + SSE), frontend/ (HTML + Alpine)
examples/       fixture generators, full_loop.sh, the committed vector cache
examples/bigquery/  the corpus measurement scripts (see its README)
examples/onnx_embedding_bench.py  a candidate vector space, measured offline
tools/          mutate.py (do guards bite), buckets.py (test scopes),
                clustering_notebook.py (marimo: level 1, one threshold at a time)
docs/           BLUEPRINT (contract), FINDINGS (real corpora), METRICS (fixtures),
                CAPABILITIES (components), TESTING (tests), BIGQUERY (setup)
tests/          property/ + unit/, hypothesis for the invariants
```
