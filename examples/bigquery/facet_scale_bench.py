"""The facet question again, at five times the resolution, on real controls.

`facet_prompt_bench.py` answered WHICH facet mechanism wins, on 276 components
against a derangement. Two things about that answer are weak, and this script
fixes both:

  * **The controls were synthetic.** A derangement pairs two unrelated
    components, which is easy — every method scored above 87%, titles reached
    99.3%. Real controls come from `corpus_b_control.parquet`: same users, same
    elapsed-time range, no duplicate ruling. They are much harder, and they are
    the ones the published bench uses.
  * **300 control pairs cannot resolve a 1% budget.** Three pairs set the
    threshold, so the 1% column was a three-pair measurement wearing a
    percentage. 1,500 controls put 15 pairs there.

SCALE, and it is a deliberate middle. The full corpus is 21,473 pairs and 39,280
distinct titles, so facets for all of it is 38,092 generation calls. This runs
3,000 pairs — about 4,800 generations — which is five times the resolution of
the 276-component bench at an eighth of the full cost. What it cannot do is
settle the far tail; that is stated rather than implied.

GENERATION IS BATCHED. `make_facets.py` calls the model once per facet through
`get_fingerprint_llm()`, which is right for a pilot and would take roughly two
hours here. This goes through `ML.GENERATE_TEXT` against a remote model in the
same dataset, so 4,800 generations are one query.

FOUR METHODS, the same four as the prompt bench, so the two tables can be read
side by side:

  title-jaccard   free, no model
  title-cosine    embed the raw title
  facet-cosine    embed the generated facet
  facet-redacted  embed the facet after §d's mechanical redaction

SPACE: `bigquery:gemini-embedding-001:768`, as everywhere else here.
"""
import re
import sys
import time

import numpy as np
import pandas as pd
from google.cloud import bigquery

import bqconfig
from facet_prompt_bench import REDACTION, long_numbers, proper_nouns, redact

P = bqconfig.dataset()
c = bigquery.Client(project=bqconfig.project())
D = "examples/bigquery/data"

BUDGETS = (0.101, 0.05, 0.01)

#: Pairs per corpus. 1,500 + 1,500 puts 15 control pairs at the 1% budget, where
#: the 276-component bench had 3. Raising this is linear in generation cost.
N_PER_CORPUS = 1500

#: Fixed so a re-run measures the method rather than a new sample of pairs.
SEED = 24

#: The relaxed prompt, which `facet_prompt_bench.py` measured as the better of
#: the two on disk. It is reproduced here rather than imported because
#: `make_facets.py` holds the strict one, and a bench that silently used a
#: different prompt from the one it names would be worthless.
PROMPT = """You are given a question someone asked on a technical forum.

Write ONE sentence describing the KIND of task it represents.

- Describe the task, not this instance of it.
- Do not quote the question.
- Someone who cannot see the question must understand your sentence completely.
- Name the technologies involved when they matter to the kind of task.

Question: {title}

Sentence:"""


def sample_pairs() -> pd.DataFrame:
    """1,500 duplicate pairs and 1,500 matched controls, from the real corpora."""
    A = pd.read_parquet(f"{D}/corpus_a_selfdup.parquet")
    B = pd.read_parquet(f"{D}/corpus_b_control.parquet")
    rng = np.random.default_rng(SEED)
    a = A.iloc[rng.choice(len(A), size=min(N_PER_CORPUS, len(A)), replace=False)]
    b = B.iloc[rng.choice(len(B), size=min(N_PER_CORPUS, len(B)), replace=False)]
    return pd.concat([
        pd.DataFrame({"corpus": "A", "ta": a.dup_title.values, "tb": a.orig_title.values}),
        pd.DataFrame({"corpus": "B", "ta": b.title_a.values, "tb": b.title_b.values}),
    ], ignore_index=True)


def jaccard(a: str, b: str) -> float:
    sa, sb = set(a.lower().split()), set(b.lower().split())
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def generate_facets(titles: list[str]) -> dict[str, str]:
    """One facet per title, in one batched query.

    A generation that comes back empty is dropped rather than replaced by the
    title: substituting the source would quietly turn a facet row into a title
    row and inflate the facet method with the baseline's own signal.
    """
    frame = pd.DataFrame({"title": titles})
    c.load_table_from_dataframe(
        frame, f"{P}.r25_titles",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    ).result()

    t0 = time.perf_counter()
    c.query(f"""
    CREATE OR REPLACE TABLE `{P}.r25_facets` AS
    SELECT title, ml_generate_text_llm_result AS facet
    FROM ML.GENERATE_TEXT(
      MODEL `{P}.gen_gemini_flash`,
      (SELECT title, CONCAT({PROMPT.split('{title}')[0]!r}, title,
                            {PROMPT.split('{title}')[1]!r}) AS prompt
       FROM `{P}.r25_titles`),
      STRUCT(0.0 AS temperature, 120 AS max_output_tokens,
             TRUE AS flatten_json_output))
    """, location="EU").result()
    print(f"  generated {len(titles):,} facets in {time.perf_counter() - t0:.0f}s")

    out = {}
    for r in c.query(f"SELECT title, facet FROM `{P}.r25_facets`", location="EU").result():
        text = (r["facet"] or "").strip()
        if text:
            out[r["title"]] = " ".join(text.split())
    print(f"  usable: {len(out):,} of {len(titles):,} "
          f"({len(out) / len(titles) * 100:.1f}%)")
    return out


def embed(texts: list[str]) -> dict[str, np.ndarray]:
    frame = pd.DataFrame({"content": texts})
    c.load_table_from_dataframe(
        frame, f"{P}.r25_texts",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    ).result()
    t0 = time.perf_counter()
    c.query(f"""
    CREATE OR REPLACE TABLE `{P}.r25_emb` AS
    SELECT content, ml_generate_embedding_result AS v
    FROM ML.GENERATE_EMBEDDING(
      MODEL `{P}.emb_gemini_embedding_001`,
      (SELECT content FROM `{P}.r25_texts`),
      STRUCT(768 AS output_dimensionality, TRUE AS flatten_json_output))
    """, location="EU").result()
    print(f"  embedded {len(texts):,} texts in {time.perf_counter() - t0:.0f}s")

    vec = {}
    for r in c.query(f"SELECT content, v FROM `{P}.r25_emb`", location="EU").result():
        v = np.asarray(r["v"], dtype=float)
        n = np.linalg.norm(v)
        vec[r["content"]] = v / n if n else v
    return vec


def recall_at(a: np.ndarray, b: np.ndarray, fp: float) -> float:
    return float((a >= float(np.quantile(b, 1 - fp))).mean())


def main() -> None:
    pairs = sample_pairs()
    titles = sorted(set(pairs.ta) | set(pairs.tb))
    print(f"pairs: {len(pairs)}  A={int((pairs.corpus == 'A').sum())} "
          f"B={int((pairs.corpus == 'B').sum())}   distinct titles: {len(titles):,}")

    facet = generate_facets(titles)
    kept = pairs[pairs.ta.isin(facet) & pairs.tb.isin(facet)].reset_index(drop=True)
    print(f"pairs with a facet on both sides: {len(kept)} "
          f"(A={int((kept.corpus == 'A').sum())} B={int((kept.corpus == 'B').sum())})")

    fa = [facet[t] for t in kept.ta]
    fb = [facet[t] for t in kept.tb]
    ra = [redact(x) for x in fa]
    rb = [redact(x) for x in fb]

    vec = embed(sorted(set(list(kept.ta) + list(kept.tb) + fa + fb + ra + rb)))
    cos = lambda x, y: float(np.dot(vec[x], vec[y]))

    methods = {
        "title-jaccard": np.array([jaccard(a, b) for a, b in zip(kept.ta, kept.tb)]),
        "title-cosine": np.array([cos(a, b) for a, b in zip(kept.ta, kept.tb)]),
        "facet-cosine": np.array([cos(a, b) for a, b in zip(fa, fb)]),
        "facet-redacted": np.array([cos(a, b) for a, b in zip(ra, rb)]),
    }

    is_a = (kept.corpus == "A").values
    print()
    head = "method".ljust(16) + "".join(f"@{b:.1%} FP".rjust(12) for b in BUDGETS) + "     AUC"
    print(head)
    print("-" * len(head))
    for name, s in methods.items():
        a, b = s[is_a], s[~is_a]
        row = [recall_at(a, b, fp) for fp in BUDGETS]
        rank = pd.Series(np.concatenate([a, b])).rank().values
        auc = (rank[: len(a)].sum() - len(a) * (len(a) + 1) / 2) / (len(a) * len(b))
        print(name.ljust(16) + "".join(f"{v * 100:11.1f}%" for v in row) + f"  {auc:7.4f}")

    print()
    print("leak, per facet, mean")
    for name, texts in (("facet", fa + fb), ("facet-redacted", ra + rb)):
        pn = np.mean([len(proper_nouns(t)) for t in texts])
        ln = np.mean([len(long_numbers(t)) for t in texts])
        print(f"  {name.ljust(16)} proper nouns {pn:5.2f}   long numbers {ln:5.2f}")

    n_ctrl = int((~is_a).sum())
    print(f"\n  control pairs at the 1% budget: {n_ctrl * 0.01:.0f} "
          f"(of {n_ctrl}) — the resolution this run buys")


if __name__ == "__main__":
    sys.exit(main())
