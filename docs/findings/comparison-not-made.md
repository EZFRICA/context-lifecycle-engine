## The comparison this file does NOT make


**No embedding model has been benchmarked against the CLE's own.** Every bench
above runs on BigQuery, and `gemini-embedding-2` has no BigQuery remote-model
endpoint, so it cannot appear in a BigQuery bench at all. (It is reachable on
the Vertex API directly, which is what makes a bench in the CLE's space
possible in principle.) The models that can be
compared there (`text-embedding-005`, `text-multilingual-embedding-002`, MiniLM,
`gemini-embedding-001`) are compared against each other, never against the one
the engine runs on.

```
frozen cache vs gemini-embedding-2   : 1.000000
frozen cache vs gemini-embedding-001 : 0.040084
```

Reproduce the second line with:

```bash
uv run python examples/bigquery/space_identity.py
```

which re-measures the comparison over 20 texts and reports the distribution
rather than a single number:

```
norme L2 BigQuery : min=0.572648 max=0.599283
cosinus(cache, BigQuery) : min=-0.010125 med=0.036984 max=0.083587
vecteurs identiques a 1e-6 : 0/20
```

0.040084 sits inside that distribution, so the headline figure is corroborated;
what the re-measurement adds is that **no vector matches at all** (0 of 20) and
that the BigQuery norms sit at 0.57 to 0.60, which is what `assert_unit_norm`
refuses.

The only model present on both surfaces is `gemini-embedding-001`, and it is not
the CLE's. Answering "is there a better embedder for this?" needs a bench that
does not go through BigQuery.

---
