"""Generate agent facets from real clusters — PILOT, nothing integrated.

Implements the prompt half of `docs/proposals/facet-contract.md` and nothing
else: no `Facet` type, no topology write, no CLI surface. The contract's four
mechanical guards (§d) are deliberately NOT built here — this run measures what
the prompt alone produces, which is exactly what §b says cannot be trusted.
Task 3 measures the leak.

Space and model are pinned: clusters come from `bigquery:gemini-embedding-001:768`
at threshold 0.75 (uncalibrated for that space, and said so), generation from the
configured Gemini chat model.
"""
import sys, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from cle.build.fingerprinter import response_text  # noqa: E402
from cle.llm_provider import get_fingerprint_llm  # noqa: E402

D = "examples/bigquery/data"

PROMPT = """You are writing a one-sentence description of a RECURRING TASK that a
person asks an assistant to do. You will be shown several examples of that task.

Write ONE sentence, in ENGLISH, 40 to 300 characters, starting with a verb,
describing WHAT THE TASK IS — not who the person is, not the subject area.
Good: "Drafts weekly project recaps for a team, listing shipped and blocked items."
Bad: "Project management." / "A user who works in marketing."

HARD RULES, all of them:
- NEVER reproduce any private information.
- NEVER use a proper noun of any kind: no person, company, product, place, or
  framework name. Describe the KIND of thing instead.
- NEVER quote. You describe a kind of task, never one instance of it.
- Someone who cannot see the examples must understand your sentence completely.
  Anything that only makes sense with the examples in front of you is wrong.

Examples of the task:
{examples}

Your one sentence:"""


def clusters_for(users: list[str], vectors: dict, openers: pd.DataFrame, thr=0.75):
    out = []
    for u, g in openers[openers.hashed_ip.isin(users)].groupby("hashed_ip"):
        cents, members = [], []
        for r in g.itertuples():
            v = vectors.get(r.conversation_hash)
            if v is None:
                continue
            best, bs = -1, -1.0
            for i, c in enumerate(cents):
                s = float(v @ c)
                if s > bs:
                    best, bs = i, s
            if best >= 0 and bs >= thr:
                members[best].append(r.text)
                n = len(members[best])
                cents[best] = (cents[best] * (n - 1) + v) / n
                cents[best] /= np.linalg.norm(cents[best])
            else:
                cents.append(v); members.append([r.text])
        for m in members:
            if len(m) >= 3:
                out.append({"user": u, "n": len(m), "episodes": m})
    return out


def main() -> None:
    n_users = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    prefix = sys.argv[2] if len(sys.argv) > 2 else "probe10"
    op = pd.read_parquet(f"{D}/{prefix}_openers.parquet")
    em = pd.read_parquet(f"{D}/{prefix}_emb.parquet")
    if "conversation_hash" in em.columns:
        V = {r.conversation_hash: np.asarray(r.v, dtype=np.float64) for r in em.itertuples()}
    else:
        byt = {r.text: np.asarray(r.v, dtype=np.float64) for r in em.itertuples()}
        V = {r.conversation_hash: byt[r.text] for r in op.itertuples() if r.text in byt}
    V = {k: v / np.linalg.norm(v) for k, v in V.items() if np.linalg.norm(v) > 0}
    users = list(op.hashed_ip.unique())[:n_users]
    groups = clusters_for(users, V, op)
    print(f"{len(users)} utilisateurs -> {len(groups)} clusters >=3", flush=True)

    llm = get_fingerprint_llm()
    rows, t0 = [], time.perf_counter()
    for i, g in enumerate(groups):
        ex = "\n".join(f"- {t[:300]}" for t in g["episodes"][:6])
        try:
            # `.content` is a LIST OF BLOCKS, not a string — `.strip()` on it
            # raises AttributeError, and the first pilot recorded 52 fast
            # failures that looked exactly like 52 fast successes. The repo
            # already has the helper the fingerprinter uses.
            facet = response_text(llm.invoke(PROMPT.format(examples=ex)).content).strip()
        except Exception as error:
            facet = f"__ERROR__ {type(error).__name__}"
        rows.append({**g, "facet": facet})
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(groups)}  {time.perf_counter()-t0:.0f}s", flush=True)
    el = time.perf_counter() - t0
    pd.DataFrame(rows).to_parquet(f"{D}/facets_{prefix}_{n_users}.parquet")
    print(f"\n{len(rows)} facettes en {el:.0f}s  ({el/max(len(rows),1):.1f}s/facette)")
    print(f"  extrapolation 200 utilisateurs : ~{len(rows)/len(users)*200:.0f} facettes, "
          f"{len(rows)/len(users)*200*el/max(len(rows),1)/60:.0f} min")


if __name__ == "__main__":
    main()
