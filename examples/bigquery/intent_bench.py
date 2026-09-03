"""The intent-level bench: facets compared on components, not on questions.

Measuring facets of QUESTIONS against a ground truth that distinguishes
QUESTIONS. Losing the instance is what a facet is asked to do, so the 27.6-point
loss was probably an upper bound.

This builds the right object. A connected component of the self-duplicate graph
is one intent a MODERATOR attested several times: q1~q2 and q2~q3 both judged
duplicates makes {q1,q2,q3} one recurring intent, not three questions.

Each component is split into two disjoint halves. A facet is generated for EACH
half — so the comparison is between two summaries of two DISJOINT sets of
episodes of the same attested intent, which is exactly the agent-facet shape.

  positives = the two halves of the same component
  negatives = halves of different components

Four keys, and the centroid line is the upper bound: what aggregation would get
if nothing crossed a summary. The gap between it and the facet line IS the cost
of the boundary, measured on the right object.
"""
import json, sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, "examples/bigquery"); sys.path.insert(0, ".")
from cle.batch_guard import assert_batch_varied  # noqa: E402
from cle.build.fingerprinter import response_text  # noqa: E402
from cle.llm_provider import get_fingerprint_llm  # noqa: E402

D = "examples/bigquery/data"

STRICT = """You are writing a one-sentence description of a RECURRING TASK that a
person asks an assistant to do. You will be shown several examples of that task.

Write ONE sentence, in ENGLISH, 40 to 300 characters, starting with a verb,
describing WHAT THE TASK IS — not who the person is, not the subject area.

HARD RULES, all of them:
- NEVER reproduce any private information.
- NEVER use a proper noun of any kind: no person, company, product, place, or
  framework name. Describe the KIND of thing instead.
- NEVER quote. You describe a kind of task, never one instance of it.
- Someone who cannot see the examples must understand your sentence completely.

Examples of the task:
{examples}

Your one sentence:"""

RELAXED = """You are writing a one-sentence description of a RECURRING TASK that a
person asks an assistant to do. You will be shown several examples of that task.

Write ONE sentence, in ENGLISH, 40 to 300 characters, starting with a verb,
describing WHAT THE TASK IS. NAME THE TECHNOLOGIES, LANGUAGES, TOOLS AND
SUBJECT DOMAINS involved — they are what makes the task recognisable.

HARD RULES:
- NEVER reproduce any private information.
- NEVER name a PERSON or an ORGANISATION, and never include an identifier,
  URL, file path, or number longer than two digits.
- NEVER quote a sentence from the examples.
- Technology, language, framework and domain names ARE allowed and encouraged.

Examples of the task:
{examples}

Your one sentence:"""


def halves(limit: int | None = None):
    comp = json.load(open(f"{D}/intent_components.json"))
    title = json.load(open(f"{D}/intent_titles.json"))
    out = []
    for key, ids in comp.items():
        texts = [title[str(i)] for i in ids if str(i) in title and title[str(i)]]
        if len(texts) < 3:
            continue
        cut = max(1, len(texts) // 2)
        out.append({"comp": key, "a": texts[:cut], "b": texts[cut:]})
        if limit and len(out) >= limit:
            break
    return out


def generate(groups, prompt, label):
    llm = get_fingerprint_llm()
    rows, t0 = [], time.perf_counter()
    for i, g in enumerate(groups):
        r = {"comp": g["comp"], "a": g["a"], "b": g["b"]}
        for side in ("a", "b"):
            ex = "\n".join(f"- {t[:300]}" for t in g[side][:6])
            try:
                r[f"facet_{side}"] = response_text(
                    llm.invoke(prompt.format(examples=ex)).content).strip()
            except Exception as error:
                r[f"facet_{side}"] = f"__ERROR__ {type(error).__name__}"
        rows.append(r)
        if (i + 1) % 40 == 0:
            print(f"  {label} {i+1}/{len(groups)}  {time.perf_counter()-t0:.0f}s", flush=True)
    facets = [r["facet_a"] for r in rows] + [r["facet_b"] for r in rows]
    assert_batch_varied(facets, label=f"facettes {label}")
    el = time.perf_counter() - t0
    print(f"{label}: {len(rows)} composantes, {len(facets)} facettes en {el:.0f}s "
          f"({el/max(len(facets),1):.2f}s/facette)", flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    variant = sys.argv[2] if len(sys.argv) > 2 else "strict"
    groups = halves(n if n > 0 else None)
    print(f"composantes retenues : {len(groups)}")
    print(f"PLAFOND GÉNÉRATION ANNONCÉ : {2*len(groups)} appels")
    df = generate(groups, STRICT if variant == "strict" else RELAXED, variant)
    df.to_parquet(f"{D}/intent_facets_{variant}_{len(groups)}.parquet")
