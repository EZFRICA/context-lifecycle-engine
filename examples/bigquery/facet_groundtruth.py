"""Do facets preserve the intent a MODERATOR judged?

Positives defined by proximity in the episode space, the same space
the facet embedding uses: the embedding key was mechanically favoured, and 51.1%
oriented without concluding. This replaces that with the one external ground
truth the project has — 11,848 Stack Overflow self-duplicate pairs, each closed
by a human moderator as a duplicate of the same user's earlier question.

The test: generate a facet for EACH question, then ask whether the facets of a
duplicate pair score closer than the facets of a matched control pair. The
bench, the matched-false-positive protocol and the lexical baseline all already
exist.

RESERVATION, carried with the result: a facet of a Stack Overflow question is
NOT a facet of an agent. What is tested is the narrower property "does an
engine-written summary preserve the intent", not the final object. The prompt is
the CONTRACT'S prompt, unchanged, shown one example instead of several — kept
identical on purpose so the mechanism under test is the same one.
"""
import sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, "examples/bigquery")
sys.path.insert(0, ".")
from cle.batch_guard import assert_batch_varied  # noqa: E402
from cle.build.fingerprinter import response_text  # noqa: E402
from cle.llm_provider import get_fingerprint_llm  # noqa: E402
from make_facets import PROMPT  # noqa: E402

D = "examples/bigquery/data"


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    A = pd.read_parquet(f"{D}/corpus_a_selfdup.parquet").sample(n, random_state=1789)
    B = pd.read_parquet(f"{D}/corpus_b_control.parquet").sample(n, random_state=1789)
    pairs = pd.concat([
        pd.DataFrame({"corpus": "A", "ta": A.dup_title.values, "tb": A.orig_title.values,
                      "jac": A.jaccard.values}),
        pd.DataFrame({"corpus": "B", "ta": B.title_a.values, "tb": B.title_b.values,
                      "jac": B.jaccard.values}),
    ], ignore_index=True)
    titles = sorted({str(x) for x in pd.concat([pairs.ta, pairs.tb]).dropna()})
    print(f"{len(pairs)} paires -> {len(titles)} titres distincts", flush=True)
    print(f"PLAFOND GÉNÉRATION ANNONCÉ : {len(titles)} appels", flush=True)

    llm = get_fingerprint_llm()
    facets, t0 = {}, time.perf_counter()
    for i, title in enumerate(titles):
        try:
            facets[title] = response_text(
                llm.invoke(PROMPT.format(examples=f"- {title[:300]}")).content).strip()
        except Exception as error:
            facets[title] = f"__ERROR__ {type(error).__name__}"
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(titles)}  {time.perf_counter()-t0:.0f}s", flush=True)
    # What the guard exists for: a batch that returns is not a batch that
    # worked, and 1,200 uniform failures take exactly as long as 1,200 successes.
    assert_batch_varied(list(facets.values()), label="facettes vérité terrain")
    pd.DataFrame({"title": list(facets), "facet": list(facets.values())}).to_parquet(
        f"{D}/facets_groundtruth.parquet")
    pairs.to_parquet(f"{D}/facets_groundtruth_pairs.parquet")
    print(f"\n{len(facets)} facettes en {time.perf_counter()-t0:.0f}s")


if __name__ == "__main__":
    main()
