"""Do facets group better than the text they were made from?

The question `docs/proposals/facet-contract.md` leaves open, and the one that
decides level 2's architecture. Clio's layer 1 replaces raw user text with a
generated facet before anything is clustered. That is a privacy mechanism first,
but it is also a claim about signal: the facet is supposed to say what KIND of
task this is, stripped of the instance. If that claim is false - if facets group
no better than the titles they came from, or no better than free string overlap
- then level 2 needs no embeddings and no generation step, and Clio's stages 2
to 4 can run on something far cheaper.

PROTOCOL, identical to `model_bench.py` so the numbers are comparable: every
method is pinned to the SAME error budget on the control corpus, then read on
the duplicates. Nothing is ever tuned on the corpus it is scored against.

  corpus A  300 pairs a moderator closed as duplicates of each other
  corpus B  300 matched control pairs, same users, no duplicate ruling

Four methods over the same 600 pairs:

  title-jaccard   free, no model. The bar every paid method has to clear.
  title-cosine    embed the raw title
  facet-jaccard   free, over the generated facet
  facet-cosine    embed the generated facet

SPACE: `bigquery:gemini-embedding-001:768`, the same as every other bench here,
NOT the CLE's `google:gemini-embedding-2:768` - median cosine between the two on
identical texts is 0.037. The engine's 0.775 threshold does not apply.

BILLS: one embedding per distinct text, ~2,376 of them, once. Re-runs read the
materialised table.
"""
import sys
import time

import numpy as np
import pandas as pd
from google.cloud import bigquery

import bqconfig

P = bqconfig.lazy_dataset()
c = bqconfig.lazy_client()
D = "examples/bigquery/data"

#: The false-positive budgets to report. 0.101 is where the Stack Overflow bench
#: pinned every model, so the facet numbers land beside the published ones; the
#: other two are there because the published bench showed the RANKING INVERTS
#: between them, and a single operating point would hide that.
BUDGETS = (0.101, 0.05, 0.01)


def jaccard(a: str, b: str) -> float:
    """Word-set overlap, the free baseline. Lowercased, split on whitespace."""
    sa, sb = set(a.lower().split()), set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def recall_at(a_scores: np.ndarray, b_scores: np.ndarray, fp: float) -> tuple[float, float]:
    """Threshold so the CONTROL fires at `fp`, then read recall on the duplicates.

    Returns (recall, threshold). The threshold comes from B and is read on A -
    that separation is the whole reason these numbers are comparable across
    methods that live on different scales (Jaccard is 0..1 over words, cosine is
    0..1 over a 768-dimension space, and they are not the same 0.7).
    """
    t = float(np.quantile(b_scores, 1 - fp))
    return float((a_scores >= t).mean()), t


def load_pairs() -> pd.DataFrame:
    """The 600 judged pairs, each with the facet generated for both sides."""
    g = pd.read_parquet(f"{D}/facets_groundtruth.parquet")
    p = pd.read_parquet(f"{D}/facets_groundtruth_pairs.parquet")
    facet = dict(zip(g.title, g.facet))

    missing = [t for t in pd.unique(pd.concat([p.ta, p.tb])) if t not in facet]
    if missing:
        # Refused rather than silently scored on a subset: a facet bench run on
        # whichever pairs happened to have a facet measures the generator's
        # coverage, not the facet's separating power.
        raise SystemExit(
            f"{len(missing)} of {p.ta.nunique() + p.tb.nunique()} titles have no facet. "
            "Regenerate with make_facets.py before benching."
        )

    p = p.copy()
    p["facet_a"] = p.ta.map(facet)
    p["facet_b"] = p.tb.map(facet)
    return p


def embed_all(texts: list[str]) -> dict[str, np.ndarray]:
    """One embedding per distinct text, through ML.GENERATE_EMBEDDING.

    Vectors come back UNNORMALISED (norm 0.57 to 0.60): BigQuery does not
    renormalise after truncating to the requested dimension. They are normalised
    here, at the boundary, so the dot product below is a cosine - the same
    correction `assert_unit_norm` refuses to make silently inside the engine.
    """
    frame = pd.DataFrame({"content": texts})
    c.load_table_from_dataframe(
        frame, f"{P}.r24_facet_texts",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    ).result()

    t0 = time.perf_counter()
    c.query(f"""
    CREATE OR REPLACE TABLE `{P}.r24_facet_emb` AS
    SELECT content, ml_generate_embedding_result AS v
    FROM ML.GENERATE_EMBEDDING(
      MODEL `{P}.emb_gemini_embedding_001`,
      (SELECT content FROM `{P}.r24_facet_texts`),
      STRUCT(768 AS output_dimensionality, TRUE AS flatten_json_output))
    """, location=bqconfig.region().upper() if hasattr(bqconfig, "region") else "EU").result()
    print(f"  embedded {len(texts):,} texts in {time.perf_counter() - t0:.0f}s")

    rows = c.query(f"SELECT content, v FROM `{P}.r24_facet_emb`",
                   location="EU").result()
    out = {}
    for r in rows:
        v = np.asarray(r["v"], dtype=float)
        n = np.linalg.norm(v)
        out[r["content"]] = v / n if n else v
    return out


def main() -> None:
    pairs = load_pairs()
    print(f"pairs: {len(pairs)}  A={int((pairs.corpus == 'A').sum())} "
          f"B={int((pairs.corpus == 'B').sum())}")

    texts = sorted(set(pairs.ta) | set(pairs.tb) | set(pairs.facet_a) | set(pairs.facet_b))
    vec = embed_all(texts)

    cos = lambda x, y: float(np.dot(vec[x], vec[y]))
    methods = {
        "title-jaccard": np.array([jaccard(a, b) for a, b in zip(pairs.ta, pairs.tb)]),
        "title-cosine": np.array([cos(a, b) for a, b in zip(pairs.ta, pairs.tb)]),
        "facet-jaccard": np.array([jaccard(a, b) for a, b in zip(pairs.facet_a, pairs.facet_b)]),
        "facet-cosine": np.array([cos(a, b) for a, b in zip(pairs.facet_a, pairs.facet_b)]),
    }

    is_a = (pairs.corpus == "A").values
    print()
    header = "method".ljust(16) + "".join(f"@{b:.1%} FP".rjust(12) for b in BUDGETS) + "     AUC"
    print(header)
    print("-" * len(header))
    results = {}
    for name, scores in methods.items():
        a, b = scores[is_a], scores[~is_a]
        row = [recall_at(a, b, fp)[0] for fp in BUDGETS]
        order = pd.Series(np.concatenate([a, b])).rank().values
        auc = (order[: len(a)].sum() - len(a) * (len(a) + 1) / 2) / (len(a) * len(b))
        results[name] = (row, auc)
        print(name.ljust(16) + "".join(f"{v * 100:11.1f}%" for v in row) + f"  {auc:7.4f}")

    print()
    for i, fp in enumerate(BUDGETS):
        best = max(results, key=lambda k: results[k][0][i])
        gain = (results["facet-cosine"][0][i] - results["title-jaccard"][0][i]) * 100
        print(f"  @{fp:.1%} FP  best: {best:<16} "
              f"facet-cosine over free title-jaccard: {gain:+.1f} points")


if __name__ == "__main__":
    sys.exit(main())
