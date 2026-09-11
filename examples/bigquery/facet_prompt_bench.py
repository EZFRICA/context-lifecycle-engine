"""The facet trade-off, on both axes at once: what it hides, and what it groups.

`facet_bench.py` measured one prompt and found it costs 24 points of separation
against raw titles. That is half a finding. The other half is the question it
raises: is the cost a property of facets, or of how generic THIS prompt is?

Two prompts already exist over the same 276 ground-truth components - `strict`
and `relaxed` - and they differ exactly along the axis that matters. The relaxed
one names Apache, Perl, CPAN; the strict one says "a web server environment".
So the pair measures the slope rather than a point.

TWO AXES, and the whole reason this script exists is that they move together:

  * GROUPING - recall at a matched false-positive rate, the same protocol as
    every other bench here. Higher is better.
  * LEAK - the mechanical checks `docs/proposals/facet-contract.md` §d specifies
    and that were never built: proper nouns, long numbers, and verbatim spans
    from the source. Lower is better.

The contract calls the prompt instruction "the weakest link in the design" and
says a prompt instruction is not a guard. This does not turn §d into a guard; it
runs those checks as a MEASUREMENT, on two prompts, so the trade has numbers on
both sides instead of an assertion on one.

CONTROLS ARE BUILT, NOT DRAWN. The component file holds positives only: each row
is one moderator-linked group, side `a` against side `b`. A control is therefore
`facet_a[i]` against `facet_b[j]` for i != j - two sides of two unrelated
groups. Same construction for both prompts and for the title baseline, so the
comparison is between methods and not between control sets.

SPACE: `bigquery:gemini-embedding-001:768`, as everywhere else here.
BILLS: one embedding per distinct text. Nothing is generated; both prompts'
output is already on disk.
"""
import re
import sys
import time

import numpy as np
import pandas as pd
from google.cloud import bigquery

import bqconfig

P = bqconfig.lazy_dataset()
c = bqconfig.lazy_client()
D = "examples/bigquery/data"

BUDGETS = (0.101, 0.05, 0.01)

#: Deterministic control pairing. The seed is fixed so a re-run measures the
#: prompts rather than a new draw of negatives.
SEED = 23

#: The mechanical §d checks live in the engine (`cle.population.leak`), where
#: the facet type and the name screen use them. Re-exported so every caller of
#: this module and every reference in the docs still resolves.
from cle.population.leak import (  # noqa: E402
    REDACTION,
    _STOP_CAPS,
    long_numbers,
    proper_nouns,
    redact,
    verbatim_spans,
)

def recall_at(a: np.ndarray, b: np.ndarray, fp: float) -> float:
    return float((a >= float(np.quantile(b, 1 - fp))).mean())


def as_text(cell) -> str:
    """A component side is an array of titles; join it into one text."""
    if isinstance(cell, (list, tuple, np.ndarray)):
        return " ".join(str(x) for x in cell)
    return str(cell)


def main() -> None:
    strict = pd.read_parquet(f"{D}/intent_facets_strict_full.parquet")
    relaxed = pd.read_parquet(f"{D}/intent_facets_relaxed_full.parquet")
    if not (strict.comp.tolist() == relaxed.comp.tolist()):
        raise SystemExit("the two prompt files do not cover the same components")

    n = len(strict)
    rng = np.random.default_rng(SEED)
    # A derangement: every control pairs side a of one component with side b of
    # a DIFFERENT one, and no index maps to itself.
    shuffled = rng.permutation(n)
    while (shuffled == np.arange(n)).any():
        shuffled = rng.permutation(n)

    methods = {
        "title (no facet)": (strict.a.map(as_text).tolist(), strict.b.map(as_text).tolist()),
        "facet · strict": (strict.facet_a.tolist(), strict.facet_b.tolist()),
        "facet · relaxed": (relaxed.facet_a.tolist(), relaxed.facet_b.tolist()),
        "facet · relaxed+redacted": ([redact(x) for x in relaxed.facet_a],
                                     [redact(x) for x in relaxed.facet_b]),
    }

    texts = sorted({t for left, right in methods.values() for t in left + right})
    print(f"components: {n}   positives: {n}   controls: {n} (derangement, seed {SEED})")
    print(f"distinct texts to embed: {len(texts):,}")

    frame = pd.DataFrame({"content": texts})
    c.load_table_from_dataframe(
        frame, f"{P}.r24_prompt_texts",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    ).result()
    t0 = time.perf_counter()
    c.query(f"""
    CREATE OR REPLACE TABLE `{P}.r24_prompt_emb` AS
    SELECT content, ml_generate_embedding_result AS v
    FROM ML.GENERATE_EMBEDDING(
      MODEL `{P}.emb_gemini_embedding_001`,
      (SELECT content FROM `{P}.r24_prompt_texts`),
      STRUCT(768 AS output_dimensionality, TRUE AS flatten_json_output))
    """, location="EU").result()
    print(f"embedded in {time.perf_counter() - t0:.0f}s")

    vec = {}
    for r in c.query(f"SELECT content, v FROM `{P}.r24_prompt_emb`", location="EU").result():
        v = np.asarray(r["v"], dtype=float)
        norm = np.linalg.norm(v)
        vec[r["content"]] = v / norm if norm else v

    cos = lambda x, y: float(np.dot(vec[x], vec[y]))

    print()
    head = "method".ljust(18) + "".join(f"@{b:.1%} FP".rjust(12) for b in BUDGETS) + "   separation"
    print(head)
    print("-" * len(head))
    grouping = {}
    for name, (left, right) in methods.items():
        pos = np.array([cos(left[i], right[i]) for i in range(n)])
        neg = np.array([cos(left[i], right[shuffled[i]]) for i in range(n)])
        row = [recall_at(pos, neg, fp) for fp in BUDGETS]
        grouping[name] = (row, pos.mean() - neg.mean())
        print(name.ljust(18) + "".join(f"{v * 100:11.1f}%" for v in row)
              + f"   {pos.mean() - neg.mean():+.3f}")

    print()
    print("leak, mechanical checks the contract specifies (per facet, mean)")
    print("prompt".ljust(18) + "proper nouns".rjust(14) + "long numbers".rjust(14)
          + "verbatim 6-grams".rjust(18))
    print("-" * 64)
    redacted = relaxed.copy()
    redacted["facet_a"] = [redact(x) for x in relaxed.facet_a]
    redacted["facet_b"] = [redact(x) for x in relaxed.facet_b]
    for name, frame_ in (("facet · strict", strict), ("facet · relaxed", relaxed),
                         ("facet · relaxed+red.", redacted)):
        facets = frame_.facet_a.tolist() + frame_.facet_b.tolist()
        sources = frame_.a.map(as_text).tolist() + frame_.b.map(as_text).tolist()
        pn = np.mean([len(proper_nouns(f)) for f in facets])
        ln = np.mean([len(long_numbers(f)) for f in facets])
        vb = np.mean([verbatim_spans(f, [s]) for f, s in zip(facets, sources)])
        print(name.ljust(18) + f"{pn:14.2f}{ln:14.2f}{vb:18.2f}")

    print()
    s_rec = grouping["facet · strict"][0][0]
    r_rec = grouping["facet · relaxed"][0][0]
    t_rec = grouping["title (no facet)"][0][0]
    x_rec = grouping["facet · relaxed+redacted"][0][0]
    print(f"  at the 10.1% budget: title {t_rec:.1%} · relaxed {r_rec:.1%} "
          f"· redacted {x_rec:.1%} · strict {s_rec:.1%}")
    print(f"  the prompt axis is worth      {(r_rec - s_rec) * 100:+.1f} points")
    print(f"  redaction costs relaxed       {(x_rec - r_rec) * 100:+.1f} points")
    print(f"  redacted vs strict, same leak {(x_rec - s_rec) * 100:+.1f} points")


if __name__ == "__main__":
    sys.exit(main())
