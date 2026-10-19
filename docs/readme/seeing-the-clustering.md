## Seeing the clustering

```bash
uv sync --all-extras --inexact          # includes the `notebook` extra
uv run marimo edit tools/clustering_notebook.py
```

A slider over the clustering threshold, on either offline corpus, in the stub
space or the committed `gemini-embedding-2` cache - and in a local ONNX space
when `$CLE_ONNX_MODEL_DIR` points at one (`examples/onnx_embedding_bench.py`
says where to get it). The grouping shown is `cle.population.grouping.group`,
the function `cle population` runs, so the picture cannot drift from the engine.
What it is for: watching purity and completeness move in opposite directions as
the threshold moves is the fastest way to see that **the threshold is a property
of the space**, which no table makes obvious.
