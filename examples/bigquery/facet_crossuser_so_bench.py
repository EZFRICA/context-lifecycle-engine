"""Level 2's question on REAL users with REAL labels: Stack Overflow, across authors.

Every previous cross-user bench here had to pick one of two compromises. The
synthetic corpus (`facet_crossuser_bench.py`) has labels but the users come from
one generator. The WildChat export (`dashboard_level_2/export_real.py`) has real
users but no labels, so it can report a similarity spread and never a recall.

Stack Overflow has both, and the repository had not noticed: **662,401 duplicate
closures link questions written by DIFFERENT authors.** A moderator ruling that
two strangers asked the same question is exactly level 2's positive - two
independent people producing the same intent. The existing `corpus_a_selfdup`
deliberately kept only the 15,026 same-author pairs, because it was built for the
detector, which sees one user at a time.

THE CONTROL IS THE HARD PART, and getting it wrong would make this bench
worthless. Two random Stack Overflow questions by different people are trivially
far apart: any method separates "how do I center a div" from "kafka consumer lag"
and the bench would report that everything works. So a control pair here is two
questions that

  * come from DIFFERENT authors, like the positives,
  * SHARE AT LEAST ONE TAG, so both sit in the same technical domain,
  * carry no duplicate link between them.

That leaves the bench measuring what level 2 needs - same intent versus merely
same subject - rather than topic detection.

FOUR METHODS, the same four as everywhere else so the tables line up:

    title-jaccard   free word overlap, no model
    title-cosine    embed the raw question title
    facet-cosine    embed a generated facet
    facet-redacted  the facet after §d's mechanical redaction

SPACE: `bigquery:gemini-embedding-001:768`.
BILLS: one generation and one embedding per distinct title, plus two scans of
`post_links` and `posts_questions`. Sampled down from 662,401 to keep it modest;
raise N_PER_CORPUS and the cost is linear.
"""
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd
from google.cloud import bigquery

import bqconfig
from cle.population.lexical import jaccard  # noqa: E402
from facet_prompt_bench import long_numbers, proper_nouns, redact

P = bqconfig.lazy_dataset()
c = bqconfig.lazy_client()
ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "examples" / "bigquery" / "data"

BUDGETS = (0.101, 0.05, 0.01)

#: Pairs per corpus. 1,500 controls put 15 pairs at the 1% budget, the same
#: resolution as `facet_scale_bench.py`, so the two are readable side by side.
N_PER_CORPUS = 1500

#: Questions kept per tag before the control self-join. The join is quadratic in
#: this number, so it is the whole cost control: 40 gives 780 candidate pairs per
#: tag, against the 2.68 trillion an unbounded join on `javascript` would build.
POOL_PER_TAG = 40

#: Fixed so a re-run measures the method rather than a new sample.
SEED = 26

PROMPT = """You are given a question someone asked on a technical forum.

Write ONE sentence describing the KIND of task it represents.

- Describe the task, not this instance of it.
- Do not quote the question.
- Someone who cannot see the question must understand your sentence completely.
- Name the technologies involved when they matter to the kind of task.

Question: {title}

Sentence:"""


def extract_pairs() -> pd.DataFrame:
    """Cross-author duplicates, and same-domain controls by different authors."""
    # SAMPLE BEFORE JOINING. An earlier version joined every question to every
    # other question sharing a first tag, then filtered. `javascript` alone holds
    # 2,315,300 questions, so that asked BigQuery to build 2.68 TRILLION pairs
    # before discarding almost all of them; the query never returned. Capping the
    # per-tag pool first makes the same sample tractable, and the cap is the only
    # thing that changed - the control's definition is identical.
    query = f"""
    WITH q AS (
      SELECT id, owner_user_id, title, SPLIT(tags, '|')[OFFSET(0)] AS first_tag
      FROM `{P}.posts_questions`
      WHERE owner_user_id IS NOT NULL AND title IS NOT NULL AND tags IS NOT NULL
    ),
    dup AS (
      SELECT qa.title AS ta, qb.title AS tb, qa.first_tag,
             CAST(qa.owner_user_id AS STRING) AS ua,
             CAST(qb.owner_user_id AS STRING) AS ub
      FROM `{P}.post_links` l
      JOIN q qa ON qa.id = l.post_id
      JOIN q qb ON qb.id = l.related_post_id
      WHERE l.link_type_id = 3
        AND qa.owner_user_id != qb.owner_user_id
        AND qa.title != qb.title
    ),
    -- Controls are drawn from the SAME tags the positives use, so the two
    -- corpora share a domain distribution and the bench cannot be won by
    -- noticing that positives are about different subjects than controls.
    dup_tags AS (SELECT DISTINCT first_tag FROM dup),
    pool AS (
      SELECT id, owner_user_id, title, first_tag
      FROM (
        SELECT q.*, ROW_NUMBER() OVER (
                 PARTITION BY q.first_tag
                 ORDER BY FARM_FINGERPRINT(CAST(q.id AS STRING))) AS rn
        FROM q JOIN dup_tags USING (first_tag)
      )
      WHERE rn <= {POOL_PER_TAG}
    ),
    linked AS (
      SELECT post_id AS lhs, related_post_id AS rhs FROM `{P}.post_links`
      UNION ALL
      SELECT related_post_id AS lhs, post_id AS rhs FROM `{P}.post_links`
    ),
    ctrl AS (
      SELECT qx.title AS ta, qy.title AS tb,
             CAST(qx.owner_user_id AS STRING) AS ua,
             CAST(qy.owner_user_id AS STRING) AS ub
      FROM pool qx
      JOIN pool qy
        ON qx.first_tag = qy.first_tag
       AND qx.owner_user_id != qy.owner_user_id
       AND qx.id < qy.id
      WHERE qx.title != qy.title
        AND NOT EXISTS (SELECT 1 FROM linked l WHERE l.lhs = qx.id AND l.rhs = qy.id)
    )
    SELECT 'A' AS corpus, ta, tb, ua, ub FROM dup
      WHERE MOD(ABS(FARM_FINGERPRINT(CONCAT(ta, tb))), 100) < 2
    UNION ALL
    SELECT 'B' AS corpus, ta, tb, ua, ub FROM ctrl
      WHERE MOD(ABS(FARM_FINGERPRINT(CONCAT(ta, tb))), 1000) < 3
    """
    t0 = time.perf_counter()
    job = c.query(query, location="EU")
    frame = job.result().to_dataframe()
    print(f"  extracted {len(frame):,} candidate pairs in {time.perf_counter()-t0:.0f}s "
          f"({job.total_bytes_billed/1e9:.2f} GB billed)")

    rng = np.random.default_rng(SEED)
    out = []
    for corpus in ("A", "B"):
        part = frame[frame.corpus == corpus]
        take = min(N_PER_CORPUS, len(part))
        out.append(part.iloc[rng.choice(len(part), size=take, replace=False)])
    return pd.concat(out, ignore_index=True)




def generate_facets(titles: list[str]) -> dict[str, str]:
    """One facet per title, batched. An empty generation is dropped, never
    replaced by the title: substituting the source would hand the facet method
    the baseline's own signal."""
    frame = pd.DataFrame({"title": titles})
    c.load_table_from_dataframe(
        frame, f"{P}.r27_so_titles",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    ).result()
    head, tail = PROMPT.split("{title}")
    t0 = time.perf_counter()
    c.query(f"""
    CREATE OR REPLACE TABLE `{P}.r27_so_facets` AS
    SELECT title, ml_generate_text_llm_result AS facet
    FROM ML.GENERATE_TEXT(
      MODEL `{P}.gen_gemini_flash`,
      (SELECT title, CONCAT({head!r}, title, {tail!r}) AS prompt
       FROM `{P}.r27_so_titles`),
      STRUCT(0.0 AS temperature, 120 AS max_output_tokens, TRUE AS flatten_json_output))
    """, location="EU").result()
    print(f"  generated {len(titles):,} facets in {time.perf_counter()-t0:.0f}s")
    out = {}
    for r in c.query(f"SELECT title, facet FROM `{P}.r27_so_facets`", location="EU").result():
        text = (r["facet"] or "").strip()
        if text:
            out[r["title"]] = " ".join(text.split())
    print(f"  usable: {len(out):,} of {len(titles):,}")
    return out


def embed(texts: list[str]) -> dict[str, np.ndarray]:
    frame = pd.DataFrame({"content": texts})
    c.load_table_from_dataframe(
        frame, f"{P}.r27_so_texts",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    ).result()
    t0 = time.perf_counter()
    c.query(f"""
    CREATE OR REPLACE TABLE `{P}.r27_so_emb` AS
    SELECT content, ml_generate_embedding_result AS v
    FROM ML.GENERATE_EMBEDDING(
      MODEL `{P}.emb_gemini_embedding_001`,
      (SELECT content FROM `{P}.r27_so_texts`),
      STRUCT(768 AS output_dimensionality, TRUE AS flatten_json_output))
    """, location="EU").result()
    print(f"  embedded {len(texts):,} texts in {time.perf_counter()-t0:.0f}s")
    vec = {}
    for r in c.query(f"SELECT content, v FROM `{P}.r27_so_emb`", location="EU").result():
        v = np.asarray(r["v"], dtype=float)
        n = np.linalg.norm(v)
        vec[r["content"]] = v / n if n else v
    return vec


def recall_at(pos: np.ndarray, neg: np.ndarray, fp: float) -> float:
    return float((pos >= float(np.quantile(neg, 1 - fp))).mean())


def project(vec, texts):
    matrix = np.array([vec[t] for t in texts])
    matrix = matrix - matrix.mean(axis=0)
    _, singular, comps = np.linalg.svd(matrix, full_matrices=False)
    xyz = matrix @ comps[:3].T
    return xyz / np.abs(xyz).max(), float((singular[:3] ** 2).sum() / (singular ** 2).sum())


def main() -> None:
    pairs = extract_pairs()
    print(f"pairs: {len(pairs)}  A={int((pairs.corpus=='A').sum())} "
          f"B={int((pairs.corpus=='B').sum())}")

    titles = sorted(set(pairs.ta) | set(pairs.tb))
    facets = generate_facets(titles)
    kept = pairs[pairs.ta.isin(facets) & pairs.tb.isin(facets)].reset_index(drop=True)
    print(f"pairs with a facet on both sides: {len(kept)} "
          f"(A={int((kept.corpus=='A').sum())} B={int((kept.corpus=='B').sum())})")

    fa = [facets[t] for t in kept.ta]
    fb = [facets[t] for t in kept.tb]
    ra, rb = [redact(x) for x in fa], [redact(x) for x in fb]
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
    scores = {}
    for name, s in methods.items():
        pos, neg = s[is_a], s[~is_a]
        row = [recall_at(pos, neg, fp) for fp in BUDGETS]
        rank = pd.Series(np.concatenate([pos, neg])).rank().values
        auc = (rank[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
        scores[name] = {str(fp): round(v * 100, 1) for fp, v in zip(BUDGETS, row)}
        scores[name]["auc"] = round(auc, 4)
        print(name.ljust(16) + "".join(f"{v*100:11.1f}%" for v in row) + f"  {auc:7.4f}")

    print()
    print("leak, per facet, mean")
    for name, texts in (("facet", fa + fb), ("facet-redacted", ra + rb)):
        print(f"  {name.ljust(16)} proper nouns "
              f"{np.mean([len(proper_nouns(t)) for t in texts]):5.2f}   "
              f"long numbers {np.mean([len(long_numbers(t)) for t in texts]):5.2f}")

    # A view for the board: one point per DISTINCT question, so the plot shows
    # questions rather than pairs.
    # One point per DISTINCT question, carrying its author. The author is what
    # the k-anonymity floor counts, so an export that drops it makes the floor
    # unenforceable on this corpus - which is exactly the defect this line fixes.
    seen, order, owner = set(), [], {}
    for title, user in list(zip(kept.ta, kept.ua)) + list(zip(kept.tb, kept.ub)):
        if title not in seen:
            seen.add(title); order.append(title); owner[title] = str(user)
    order = order[:400]
    views = {}
    for name, src in (("text", {t: t for t in order}),
                      ("facet", {t: facets[t] for t in order}),
                      ("facet-redacted", {t: redact(facets[t]) for t in order})):
        xyz, variance = project(vec, [src[t] for t in order])
        views[name] = {"variance": round(variance, 3),
                       "points": [{"user": owner.get(t, ""), "intent": "",
                                   "x": round(float(x), 4),
                                   "y": round(float(y), 4), "z": round(float(z), 4),
                                   "facet": facets[t], "n": 1}
                                  for t, (x, y, z) in zip(order, xyz)]}

    target = ROOT / "dashboard_level_2" / "data" / "so_view.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "source": "Stack Overflow, cross-author moderator duplicates",
        "labelled": True, "views": views, "scores": scores,
        "pairs": int(len(kept)), "positives": int(is_a.sum()),
    }, ensure_ascii=False), encoding="utf-8")
    print(f"\n  -> {target.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
