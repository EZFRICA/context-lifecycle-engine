"""Task 3.1 — isolate the pairs the lexical baseline cannot see.

CLE need. The lexical baseline already separates duplicates from controls at
62.2% recall / 10.1% false positives, for zero cost. So an embedding measured on
the FULL corpus would be diluted by the ~85% Jaccard already catches, and would
report a win it did not earn.

The pairs that decide are the ones with ZERO significant-token overlap: a
moderator judged them the same question and no lexical method can see it. This
writes them out, with the matching slice of the control.
"""
import re
import pandas as pd

STOP = set("a an the how do i to in on for of and or is are can my me with using "
           "when why what get not it this that if from at as be by".split())


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9#+.]+", (text or "").lower())
            if w not in STOP and len(w) > 1}


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0


D = "examples/bigquery/data"
A = pd.read_parquet(f"{D}/corpus_a_selfdup.parquet")
B = pd.read_parquet(f"{D}/corpus_b_control.parquet")
A["jaccard"] = [jaccard(x, y) for x, y in zip(A.dup_title, A.orig_title)]
B["jaccard"] = [jaccard(x, y) for x, y in zip(B.title_a, B.title_b)]

az, bz = A[A.jaccard == 0].copy(), B[B.jaccard == 0].copy()
az.to_parquet(f"{D}/corpus_a_zero_overlap.parquet")
bz.to_parquet(f"{D}/corpus_b_zero_overlap.parquet")
A.to_parquet(f"{D}/corpus_a_selfdup.parquet")
B.to_parquet(f"{D}/corpus_b_control.parquet")

print(f"A zero-overlap : {len(az):,} / {len(A):,}  ({len(az)/len(A):.1%})")
print(f"B zero-overlap : {len(bz):,} / {len(B):,}  ({len(bz)/len(B):.1%})")
print(f"\nA zero-overlap gap (h) : p25={az.gap_hours.quantile(.25):.0f} "
      f"med={az.gap_hours.median():.0f} p75={az.gap_hours.quantile(.75):.0f}")
print(f"B zero-overlap gap (h) : p25={bz.gap_hours.quantile(.25):.0f} "
      f"med={bz.gap_hours.median():.0f} p75={bz.gap_hours.quantile(.75):.0f}")
print(f"\ntitle length (chars) A={az.dup_title.str.len().median():.0f} "
      f"B={bz.title_a.str.len().median():.0f}")
