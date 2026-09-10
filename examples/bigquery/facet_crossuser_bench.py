"""The task level 2 actually does: grouping intents ACROSS users.

Every facet bench before this one measured within-user separation, which is the
detector's job, not level 2's. Level 2 reads many independent topologies and asks
whether two of them carry the SAME recurring intent. That question has a
different negative - two strangers' unrelated intents, not two questions the same
person asked a week apart - and Part 4 showed the negative is what decides the
answer.

GROUND TRUTH, by construction rather than by judgement. `make_multiuser.py`
partitions the GDG corpus into 12 synthetic users by a seeded draw, and every
message carries its intent in `thread_id` (`events-0-0` -> `events`). So:

    positive   user A's `newsletter` cluster  vs  user B's `newsletter` cluster
    negative   user A's `newsletter` cluster  vs  user B's `sponsors` cluster

No labelling, no moderator, no judgement call. Both sides always come from
DIFFERENT users, so a method cannot win by recognising a writing style it has
already seen on the other side of the pair.

**UPPER BOUND, NEVER AN ESTIMATE.** `make_multiuser.py` says it in its own
docstring and it governs every number here: the users are slices of one
generator's output, so two users sharing a planted intent carry text from the
same generator and sit closer than two real users would. Read every figure below
as a ceiling. A method that loses here has no chance on real users; a method that
wins here has not been shown to win anywhere else.

Background traffic (`qa`, `noise`, `abandon`) is excluded from the pairing: it is
present for every user by construction, so pairing it would manufacture
positives out of the corpus's own scaffolding.

FOUR METHODS, the same four as `facet_scale_bench.py`:

    text-jaccard    free, over the cluster's concatenated episodes
    text-cosine     embed the concatenated episodes
    facet-cosine    embed one generated facet per cluster - Clio's layer 1
    facet-redacted  the facet after §d's mechanical redaction

SPACE: `bigquery:gemini-embedding-001:768`, as everywhere else here.
"""
import collections
import itertools
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

BUDGETS = (0.101, 0.05, 0.01)

#: Present for every user by construction. Pairing these would measure the
#: corpus's scaffolding rather than any recurring intent.
BACKGROUND = {"qa", "noise", "abandon"}

#: Fixed so a re-run measures the method, not a new draw of pairs.
SEED = 25

PROMPT = """You are given several requests one person made to an assistant.

Write ONE sentence describing the KIND of recurring task they represent.

- Describe the task, not these instances of it.
- Do not quote the requests.
- Someone who cannot see the requests must understand your sentence completely.
- Name the tools or domains involved when they matter to the kind of task.

Requests:
{episodes}

Sentence:"""


#: Repository root, resolved from this file rather than from the working
#: directory. The fixture glob used to be relative, so running this from
#: anywhere but the root found no files, built an empty frame, and BigQuery
#: created a 0-row table with FLOAT columns - surfacing as "ML.GENERATE_TEXT
#: expects a `prompt` column" three calls later, which names neither the missing
#: fixtures nor the directory.
ROOT = pathlib.Path(__file__).resolve().parents[2]


def load_clusters() -> dict[tuple[str, str], list[str]]:
    """(user, intent) -> its episode texts, from the committed multiuser fixture."""
    out: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    paths = sorted(ROOT.glob("examples/ph12_user*.jsonl"))
    if not paths:
        # Refused rather than returning {}: an empty result here produces a
        # confusing failure deep inside BigQuery instead of naming the cause.
        raise SystemExit(
            f"no ph12_user*.jsonl fixtures under {ROOT / 'examples'}. "
            "Regenerate them: uv run python examples/make_multiuser.py --users 12 --prefix ph12"
        )
    for path in paths:
        user = path.stem.split("_")[-1]
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            intent = row["thread_id"].split("-")[0]
            if intent not in BACKGROUND:
                out[(user, intent)].append(row["text"])
    return dict(out)


def build_pairs(clusters: dict[tuple[str, str], list[str]]) -> pd.DataFrame:
    """Every cross-user cluster pair, labelled by whether the intents match."""
    keys = sorted(clusters)
    rows = []
    for (ua, ia), (ub, ib) in itertools.combinations(keys, 2):
        if ua == ub:
            continue  # within-user: a different question, already measured
        rows.append({"ua": ua, "ia": ia, "ub": ub, "ib": ib,
                     "corpus": "A" if ia == ib else "B"})
    frame = pd.DataFrame(rows)
    # Controls outnumber positives ~6:1 here. Left as is: the protocol reads a
    # QUANTILE of the control distribution, which does not care about the count,
    # and discarding negatives to balance would throw away the resolution that
    # makes the 1% budget meaningful.
    return frame


def generate_facets(clusters: dict[tuple[str, str], list[str]]) -> dict[tuple[str, str], str]:
    """One facet per cluster, batched. Clio's layer 1, applied per user."""
    keys = sorted(clusters)
    prompts = []
    for k in keys:
        episodes = "\n".join(f"- {t}" for t in clusters[k][:12])
        prompts.append(PROMPT.format(episodes=episodes))
    frame = pd.DataFrame({"key": [f"{u}|{i}" for u, i in keys], "prompt": prompts})
    c.load_table_from_dataframe(
        frame, f"{P}.r26_cluster_prompts",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    ).result()
    t0 = time.perf_counter()
    c.query(f"""
    CREATE OR REPLACE TABLE `{P}.r26_cluster_facets` AS
    SELECT key, ml_generate_text_llm_result AS facet
    FROM ML.GENERATE_TEXT(
      MODEL `{P}.gen_gemini_flash`,
      (SELECT key, prompt FROM `{P}.r26_cluster_prompts`),
      STRUCT(0.0 AS temperature, 120 AS max_output_tokens,
             TRUE AS flatten_json_output))
    """, location="EU").result()
    print(f"  generated {len(keys)} cluster facets in {time.perf_counter() - t0:.0f}s")

    out = {}
    for r in c.query(f"SELECT key, facet FROM `{P}.r26_cluster_facets`",
                     location="EU").result():
        text = (r["facet"] or "").strip()
        if text:
            u, i = r["key"].split("|", 1)
            out[(u, i)] = " ".join(text.split())
    return out


def embed(texts: list[str]) -> dict[str, np.ndarray]:
    frame = pd.DataFrame({"content": texts})
    c.load_table_from_dataframe(
        frame, f"{P}.r26_texts",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    ).result()
    t0 = time.perf_counter()
    c.query(f"""
    CREATE OR REPLACE TABLE `{P}.r26_emb` AS
    SELECT content, ml_generate_embedding_result AS v
    FROM ML.GENERATE_EMBEDDING(
      MODEL `{P}.emb_gemini_embedding_001`,
      (SELECT content FROM `{P}.r26_texts`),
      STRUCT(768 AS output_dimensionality, TRUE AS flatten_json_output))
    """, location="EU").result()
    print(f"  embedded {len(texts):,} texts in {time.perf_counter() - t0:.0f}s")
    vec = {}
    for r in c.query(f"SELECT content, v FROM `{P}.r26_emb`", location="EU").result():
        v = np.asarray(r["v"], dtype=float)
        n = np.linalg.norm(v)
        vec[r["content"]] = v / n if n else v
    return vec




def recall_at(a: np.ndarray, b: np.ndarray, fp: float) -> float:
    return float((a >= float(np.quantile(b, 1 - fp))).mean())


def main() -> None:
    clusters = load_clusters()
    pairs = build_pairs(clusters)
    print(f"users: {len({u for u, _ in clusters})}   clusters: {len(clusters)}")
    print(f"cross-user pairs: {len(pairs)}   same intent (A): "
          f"{int((pairs.corpus == 'A').sum())}   different (B): "
          f"{int((pairs.corpus == 'B').sum())}")

    facets = generate_facets(clusters)
    missing = [k for k in clusters if k not in facets]
    if missing:
        print(f"  {len(missing)} clusters got no facet; dropped from the facet rows")

    joined = {k: " ".join(v[:12]) for k, v in clusters.items()}
    red = {k: redact(v) for k, v in facets.items()}

    texts = sorted(set(joined.values()) | set(facets.values()) | set(red.values()))
    vec = embed(texts)
    cos = lambda x, y: float(np.dot(vec[x], vec[y]))

    ka = list(zip(pairs.ua, pairs.ia))
    kb = list(zip(pairs.ub, pairs.ib))
    ok = np.array([a in facets and b in facets for a, b in zip(ka, kb)])

    methods = {
        "text-jaccard": np.array([jaccard(joined[a], joined[b]) for a, b in zip(ka, kb)]),
        "text-cosine": np.array([cos(joined[a], joined[b]) for a, b in zip(ka, kb)]),
        "facet-cosine": np.array([cos(facets[a], facets[b]) if o else np.nan
                                  for a, b, o in zip(ka, kb, ok)]),
        "facet-redacted": np.array([cos(red[a], red[b]) if o else np.nan
                                    for a, b, o in zip(ka, kb, ok)]),
    }

    is_a = (pairs.corpus == "A").values
    print()
    head = "method".ljust(16) + "".join(f"@{b:.1%} FP".rjust(12) for b in BUDGETS) + "     AUC"
    print(head)
    print("-" * len(head))
    for name, s in methods.items():
        keep = ~np.isnan(s)
        a, b = s[is_a & keep], s[(~is_a) & keep]
        row = [recall_at(a, b, fp) for fp in BUDGETS]
        rank = pd.Series(np.concatenate([a, b])).rank().values
        auc = (rank[: len(a)].sum() - len(a) * (len(a) + 1) / 2) / (len(a) * len(b))
        print(name.ljust(16) + "".join(f"{v * 100:11.1f}%" for v in row) + f"  {auc:7.4f}")

    print()
    print("leak, per facet, mean")
    for name, src in (("facet", facets), ("facet-redacted", red)):
        vals = list(src.values())
        print(f"  {name.ljust(16)} proper nouns "
              f"{np.mean([len(proper_nouns(t)) for t in vals]):5.2f}   "
              f"long numbers {np.mean([len(long_numbers(t)) for t in vals]):5.2f}")

    print("\n  UPPER BOUND: one generator, synthetic users. A ceiling, not an estimate.")


if __name__ == "__main__":
    sys.exit(main())
