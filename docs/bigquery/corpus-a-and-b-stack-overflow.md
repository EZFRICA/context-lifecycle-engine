## 4. Corpus A and B, Stack Overflow

Public data, no download. Copy the two tables the extractors read into your own
dataset so they are in your region:

```bash
for t in posts_questions post_links; do
  bq --location=EU cp -f "bigquery-public-data:stackoverflow.${t}" \
     "${CLE_BQ_PROJECT}:${CLE_BQ_DATASET}.${t}"
done
```

`post_links` with `link_type_id = 3` is the moderator duplicate closure. That
column is the external ground truth behind the 67% figure: a human judgment the
detector never sees.

```bash
uv run python examples/bigquery/extract_corpus_b.py      # matched controls
uv run python examples/bigquery/extract_corpus_c.py      # 90-day recurrence windows
uv run python examples/bigquery/build_zero_overlap.py    # pairs no lexical baseline sees
uv run python examples/bigquery/embed_pairs.py           # bills: one embedding per text
```
