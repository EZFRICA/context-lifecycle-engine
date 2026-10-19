"""§6b-ter re-run in another BigQuery space: real users, real labels, new model.

`docs/findings/stack-overflow-authors.md` measures cross-AUTHOR duplicates - a
moderator ruling that two strangers asked the same question, which is exactly
level 2's positive - against same-tag different-author controls. It was measured
in `bigquery:gemini-embedding-001:768`, because that was the only embedding
model BigQuery could host. Since 2026-10-05 it can host `gemini-embedding-2`,
the model the ENGINE runs on, and `docs/findings/space-identity-bigquery.md`
shows the two surfaces return the same vectors (cosine 1.000000, 20/20).

So this re-runs the figure in the engine's own space. It changes ONE coordinate:

  * the pairs are rebuilt by `facet_crossuser_so_bench.extract_pairs`, which is
    deterministic (SEED fixed), so the sample is the same one;
  * the facets are READ from `r27_so_facets`, generated once under
    `gen_gemini_flash` and never regenerated - a facet is data, not a derivation
    (facet contract §c);
  * only the embedding model changes.

BILLS: ~2.5 GB scanned for the pair query (about 0.015 USD on demand), plus one
embedding call per distinct title and facet. No generation.

    uv run python examples/bigquery/so_rerun_space.py
    uv run python examples/bigquery/so_rerun_space.py --model emb_gemini_embedding_001
"""

import argparse
import pathlib
import sys
import time

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples" / "bigquery"))

from cle.logs import configure_logging, get_logger  # noqa: E402
from cle.population.lexical import jaccard  # noqa: E402

log = get_logger("so_rerun_space")

#: The published row, measured in `bigquery:gemini-embedding-001:768`.
PUBLISHED = {
    "title-jaccard": (0.380, 0.284, 0.142, 0.6938),
    "title-cosine": (0.611, 0.517, 0.358, 0.8491),
    "facet-cosine": (0.543, 0.427, 0.243, 0.8203),
    "facet-redacted": (0.548, 0.411, 0.242, 0.8045),
}
BUDGETS = (0.101, 0.05, 0.01)


def recall_at(positive: np.ndarray, negative: np.ndarray, budget: float) -> float:
    """Share of positives above the bar that lets `budget` of negatives through.

    The bar is read off the NEGATIVES: a bar chosen on the positives would be
    the method grading its own exam.
    """
    return float((positive >= np.quantile(negative, 1 - budget)).mean())


def auc(positive: np.ndarray, negative: np.ndarray) -> float:
    values = np.concatenate([positive, negative])
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(1, len(values) + 1)
    for value in np.unique(values):          # average over ties
        mask = values == value
        ranks[mask] = ranks[mask].mean()
    return float((ranks[: len(positive)].sum() - len(positive) * (len(positive) + 1) / 2)
                 / (len(positive) * len(negative)))


def _candidate_pairs(client, bench) -> pd.DataFrame:
    """The pair query BEFORE the bench samples it down to 3,000.

    `extract_pairs` runs the query and immediately draws its sample, so calling
    it returns 3,000 rows already chosen - the wrong 3,000 for this re-run,
    since the facets exist for another draw. The query text is read from the
    bench module so there is ONE definition of what a pair is.
    """
    source = pathlib.Path(bench.__file__).read_text()
    start = source.index('    query = f"""')
    end = source.index('"""', start + 20) + 3
    query = eval(source[start:end].strip().removeprefix("query = "),
                 {"P": bench.P, "POOL_PER_TAG": bench.POOL_PER_TAG})
    job = client.query(query, location="EU")
    frame = job.result().to_dataframe()
    print(f"candidates   : {len(frame):,} pairs from the duplicate graph "
          f"({job.total_bytes_billed / 1e9:.2f} GB billed)")
    return frame


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="emb_gemini_embedding_2",
                        help="Remote model in the dataset; the default is the engine's space.")
    args = parser.parse_args()

    from google.cloud import bigquery

    import bqconfig
    import facet_crossuser_so_bench as bench
    from facet_prompt_bench import redact

    client = bigquery.Client(project=bqconfig.project())
    # `dataset()` already carries the project, the way every bench here uses it.
    prefix = bqconfig.dataset()

    facets = {row["title"]: row["facet"] for row in
              client.query(f"SELECT title, facet FROM `{prefix}.r27_so_facets`",
                           location="EU").result()}
    print(f"facets       : {len(facets):,} committed, generated once under "
          "gen_gemini_flash and NOT regenerated here")

    # SAMPLE INSIDE THE FACETTED TITLES. The original pair list was never
    # persisted and `extract_pairs` cannot reproduce it: its query carries no
    # ORDER BY, so the seeded draw lands on a different sample every time. Drawing
    # freely then intersecting kept 672 of 3,000 pairs - a small, skewed sample.
    # Restricting the candidates first keeps the frozen facets AND a full-size
    # draw; what it costs is that this sample is not the published one, which is
    # why the published column stays where it is instead of being overwritten.
    candidates = _candidate_pairs(client, bench)
    usable = candidates[[bool(facets.get(a)) and bool(facets.get(b))
                         for a, b in zip(candidates.ta, candidates.tb)]]
    rng = np.random.default_rng(bench.SEED)
    drawn = []
    for corpus in ("A", "B"):
        part = usable[usable.corpus == corpus]
        take = min(bench.N_PER_CORPUS, len(part))
        drawn.append(part.iloc[rng.choice(len(part), size=take, replace=False)])
    pairs = pd.concat(drawn, ignore_index=True)
    print(f"pairs        : {len(pairs):,} drawn among facetted titles  "
          f"(A = cross-author duplicates: {int((pairs.corpus == 'A').sum()):,}, "
          f"B = same-tag controls: {int((pairs.corpus == 'B').sum()):,})")
    titles = sorted(set(pairs.ta) | set(pairs.tb))
    covered = titles

    texts = sorted(set(titles) | {facets[t] for t in covered}
                   | {redact(facets[t]) for t in covered})
    frame = pd.DataFrame({"content": texts})
    client.load_table_from_dataframe(
        frame, f"{prefix}.r41_so_texts",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")).result()
    started = time.perf_counter()
    job = client.query(f"""
    CREATE OR REPLACE TABLE `{prefix}.r41_so_emb` AS
    SELECT content, ml_generate_embedding_result AS v
    FROM ML.GENERATE_EMBEDDING(
      MODEL `{prefix}.{args.model}`,
      (SELECT content FROM `{prefix}.r41_so_texts`),
      STRUCT(768 AS output_dimensionality, TRUE AS flatten_json_output))
    """, location="EU")
    job.result()
    print(f"space        : bigquery:{args.model} - {len(texts):,} texts in "
          f"{time.perf_counter() - started:.0f}s ({job.total_bytes_billed / 1e9:.2f} GB billed)")

    vectors = {}
    norms = []
    for row in client.query(f"SELECT content, v FROM `{prefix}.r41_so_emb`",
                            location="EU").result():
        vector = np.asarray(row["v"], dtype=float)
        norm = float(np.linalg.norm(vector))
        norms.append(norm)
        # Normalised HERE: `cosine` is a raw dot product and is a cosine only on
        # unit vectors. gemini-embedding-001 returns 0.57-0.60 through this
        # surface; gemini-embedding-2 returns 1.0. Both are handled, explicitly.
        vectors[row["content"]] = vector / norm if norm else vector
    print(f"               raw norms min {min(norms):.4f} max {max(norms):.4f}")

    keep = [i for i, (a, b) in enumerate(zip(pairs.ta, pairs.tb))
            if facets.get(a) and facets.get(b)]
    kept = pairs.iloc[keep].reset_index(drop=True)
    if len(kept) < len(pairs):
        log.warning("%d pair(s) dropped: a title has no committed facet", len(pairs) - len(kept))

    def cosines(left, right):
        return np.array([float(np.dot(vectors[a], vectors[b])) for a, b in zip(left, right)])

    scores = {
        "title-jaccard": np.array([jaccard(a, b) for a, b in zip(kept.ta, kept.tb)]),
        "title-cosine": cosines(kept.ta, kept.tb),
        "facet-cosine": cosines([facets[t] for t in kept.ta], [facets[t] for t in kept.tb]),
        "facet-redacted": cosines([redact(facets[t]) for t in kept.ta],
                                  [redact(facets[t]) for t in kept.tb]),
    }
    is_positive = (kept.corpus == "A").values

    print()
    print("method".ljust(16) + "".join(f"@{b:.1%} FP".rjust(11) for b in BUDGETS)
          + "       AUC" + "      published @10.1%")
    for name, values in scores.items():
        positive, negative = values[is_positive], values[~is_positive]
        row = name.ljust(16) + "".join(f"{recall_at(positive, negative, b):10.1%} " for b in BUDGETS)
        print(row + f"{auc(positive, negative):10.4f}" + f"{PUBLISHED[name][0]:19.1%}")
    print("\nSame pairs, same frozen facets; only the vector space differs. The published "
          "column was measured in bigquery:gemini-embedding-001:768 and stays there.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
