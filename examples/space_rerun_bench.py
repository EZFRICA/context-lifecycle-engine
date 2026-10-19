"""Re-run the facet-boundary figure (`docs/findings/facet-boundary-cost.md`) in another space.

WHAT THIS ANSWERS. That figure ends on an open question, in its own words: the
absolute level "is conditioned on `gemini-embedding-001` and it is unknown
whether the same ordering holds in the CLE's space, which would need the facet
corpus re-embedded". This re-embeds it - in any space the engine can open - and
prints the ordering beside the published one.

IT RE-EMBEDS, IT DOES NOT REGENERATE. The facets are read from the committed
`intent_facets_{strict,relaxed}_full.parquet`, produced once under
`gemini-3.6-flash` and frozen. A facet is data, not a derivation (facet contract
§c), so regenerating would change the object being measured and make the
comparison meaningless. What changes here is ONE coordinate: the vector space.

THE OBJECT IS A COMPONENT, NOT A QUESTION. A connected component of the
self-duplicate graph is one intent a moderator attested several times; it is
split into two disjoint halves, and a facet is generated for each. So:

    positive   the two halves of the SAME component
    negative   halves of DIFFERENT components

    centroid        mean of the half's embedded titles - the upper bound, what
                    aggregation gets when nothing crosses a summary
    facet-strict    the facet written under the strict contract
    facet-relaxed   the facet written under the relaxed one

The gap between the centroid line and a facet line IS the cost of the boundary,
and it is the gap, not the level, that travels between spaces.

COSTS: nothing in `stub`, `cached` or `onnx`. In `real` it bills one embedding
call per distinct text (~1.5k here) against `gemini-embedding-2`.

    uv run python examples/space_rerun_bench.py --space onnx
    CLE_VERTEX_PROJECT=<project> uv run python examples/space_rerun_bench.py --space real
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cle.batch_guard import assert_unit_norm  # noqa: E402
from cle.population.leak import redact  # noqa: E402
from cle.population.lexical import jaccard  # noqa: E402
from cle.detect.embedders import EMBEDDER_KINDS, open_embedder  # noqa: E402
from cle.logs import configure_logging, get_logger  # noqa: E402

log = get_logger("space_rerun_bench")

DATA = ROOT / "examples" / "bigquery" / "data"
#: The budgets every cross-user figure in this repository is read at, so the
#: rows here can be put beside them without rescaling anything.
BUDGETS = (0.101, 0.05, 0.01)

#: §6b-bis, as published: 40 real WildChat users, 130 clusters, 8,128 cross-user
#: pairs, in `bigquery:gemini-embedding-001:768`. Median, p99, and the counts
#: above 0.7 and 0.8 - NOT recall: nobody has labelled which two real users share
#: an intent, so a pair above a bar is a candidate, never a correct match.
WILDCHAT_PUBLISHED = {
    "raw episodes, embedded": (0.520, 0.660, 19, 3),
    "raw episodes, word overlap": (0.023, 0.111, 0, 0),
    "facet, embedded": (0.563, 0.716, 135, 5),
    "facet, redacted": (0.563, 0.716, 135, 5),
}

#: §4, as published, in `bigquery:gemini-embedding-001:768`: cohesion inside a
#: 90-day window against pairs more than a year apart. The finding is the
#: CONTRAST between the two lines - 1.08 on the mean, 12.9 on the tail - which is
#: why an aggregator reading means "would see ~0.55 everywhere and conclude
#: nothing".
TAIL_PUBLISHED = {"mean_near": 0.5190, "mean_far": 0.4807, "mean_factor": 1.08,
                  "share_near": 0.0270, "share_far": 0.0021, "tail_factor": 12.9}

#: What the published run measured, for the line printed under the table. The
#: centroid figure is an agreement share; the facet rows are stated as points
#: below it (docs/findings/facet-boundary-cost.md).
PUBLISHED = {"centroid": 0.993, "facet-strict": 0.993 - 0.120, "facet-relaxed": 0.993 - 0.029}


def unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


def embed_all(texts: list[str], kind: str) -> dict[str, np.ndarray]:
    """One vector per DISTINCT text, through the engine's own selection point."""
    embedder = open_embedder(kind)
    distinct = list(dict.fromkeys(texts))
    started = time.perf_counter()
    if hasattr(embedder, "embed_many"):
        vectors = embedder.embed_many(distinct)
    else:
        vectors = [embedder.embed(t) for t in distinct]
    elapsed = time.perf_counter() - started
    print(f"space        : {embedder.embedder_id}")
    print(f"embedded     : {len(distinct):,} distinct texts in {elapsed:.0f}s "
          f"({elapsed / max(1, len(distinct)) * 1000:.0f} ms each)")
    table = {}
    for text, vector in zip(distinct, vectors):
        array = unit(np.asarray(vector, dtype=float))
        table[text] = array
    for text in distinct[:32]:
        assert_unit_norm(tuple(table[text]), where=embedder.embedder_id)
    return table


def recall_at_budgets(positive: np.ndarray, negative: np.ndarray) -> dict[float, float]:
    """Share of positives above the score that lets `budget` of negatives through.

    The threshold is read off the NEGATIVES, never the positives: a bar chosen
    on the positives would be the method grading its own exam.
    """
    out = {}
    for budget in BUDGETS:
        bar = np.quantile(negative, 1 - budget)
        out[budget] = float((positive >= bar).mean())
    return out


def auc(positive: np.ndarray, negative: np.ndarray) -> float:
    """Probability a random positive outranks a random negative (ties count half)."""
    order = np.argsort(np.concatenate([positive, negative]), kind="mergesort")
    ranks = np.empty(len(order), dtype=float)
    ranks[order] = np.arange(1, len(order) + 1)
    # average ranks over ties, so a method that returns one constant scores 0.5
    values = np.concatenate([positive, negative])
    for value in np.unique(values):
        mask = values == value
        ranks[mask] = ranks[mask].mean()
    rank_sum = ranks[: len(positive)].sum()
    return float((rank_sum - len(positive) * (len(positive) + 1) / 2)
                 / (len(positive) * len(negative)))


def pairs_for(frame: pd.DataFrame, vectors: dict[str, np.ndarray], column_a: str,
              column_b: str, centroid: bool) -> tuple[np.ndarray, np.ndarray]:
    """Positive and negative score vectors for one method."""
    def side(row, column):
        value = row[column]
        if centroid:
            return unit(np.mean([vectors[t] for t in value], axis=0))
        return vectors[value]

    left = [side(row, column_a) for _, row in frame.iterrows()]
    right = [side(row, column_b) for _, row in frame.iterrows()]
    positive = np.array([float(np.dot(a, b)) for a, b in zip(left, right)])
    # Every half against every OTHER component's half: the negative is what
    # decides the answer, so it is built exhaustively rather than sampled.
    negative = np.array([float(np.dot(left[i], right[j]))
                         for i in range(len(left)) for j in range(len(right)) if i != j])
    return positive, negative


def wildchat_spread(kind: str) -> int:
    """§6b-bis in another space: how close real cross-user pairs actually get.

    Reads the committed `facets_probe200_40.parquet` - 40 real WildChat users,
    130 clusters, facets generated once and frozen. The episodes are joined for
    embedding and for the lexical baseline and NEVER leave this process: this is
    the one place real user text is read, exactly as `export_real.py` says.
    """
    frame = pd.read_parquet(DATA / "facets_probe200_40.parquet")
    frame = frame[frame.facet.astype(str).str.strip() != ""].reset_index(drop=True)
    joined = [" ".join(map(str, e))[:4000] for e in frame.episodes]
    facets = [str(f) for f in frame.facet]
    redacted = [redact(f) for f in facets]

    vectors = embed_all(sorted(set(joined) | set(facets) | set(redacted)), kind)
    pairs = [(i, j) for i in range(len(frame)) for j in range(i + 1, len(frame))
             if frame.user[i] != frame.user[j]]
    print(f"clusters     : {len(frame)} from {frame.user.nunique()} real users")
    print(f"cross-user   : {len(pairs):,} pairs\n")

    rows = {
        "raw episodes, embedded": [float(np.dot(vectors[joined[i]], vectors[joined[j]]))
                                   for i, j in pairs],
        "raw episodes, word overlap": [jaccard(joined[i], joined[j]) for i, j in pairs],
        "facet, embedded": [float(np.dot(vectors[facets[i]], vectors[facets[j]]))
                            for i, j in pairs],
        "facet, redacted": [float(np.dot(vectors[redacted[i]], vectors[redacted[j]]))
                            for i, j in pairs],
    }
    header = "method".ljust(28) + "median".rjust(9) + "p99".rjust(9) + ">=0.7".rjust(8)
    print(header + ">=0.8".rjust(7) + "      published (median / >=0.7)")
    for name, scores in rows.items():
        array = np.array(scores)
        median, p99 = float(np.median(array)), float(np.quantile(array, 0.99))
        above7, above8 = int((array >= 0.7).sum()), int((array >= 0.8).sum())
        pm, _, p7, _ = WILDCHAT_PUBLISHED[name]
        print(f"{name.ljust(28)}{median:9.3f}{p99:9.3f}{above7:8d}{above8:7d}"
              f"      {pm:.3f} / {p7}")
    # A FIXED 0.7 IS NOT COMPARABLE ACROSS SPACES - the repository's own rule, and
    # the counts above show why: the same pairs sit at a different absolute level
    # in every space. So the comparison that travels is budget-matched: put the
    # bar where raw text surfaces a fixed number of pairs, then ask how many the
    # facet surfaces at that same bar.
    raw = np.array(rows["raw episodes, embedded"])
    for budget in (0.001, 0.005):
        bar = float(np.quantile(raw, 1 - budget))
        kept = int((raw >= bar).sum())
        print()
        print(f"  bar at raw text's top {budget:.1%} (cosine {bar:+.3f}, {kept} pairs):")
        for name in ("facet, embedded", "facet, redacted", "raw episodes, word overlap"):
            count = int((np.array(rows[name]) >= bar).sum())
            print(f"    {name.ljust(28)} {count:5d} pairs clear the same bar "
                  f"({count / max(1, kept):.1f}x raw text)")
    print("\nNOT recall. No label says which two real users share an intent, so a pair "
          "above a bar is a candidate; facets over-merging produces this number too.")
    return 0


def tail_vs_mean(kind: str) -> int:
    """§4 in another space: does the tail still discriminate where the mean does not?

    Same-user opener pairs from the committed `probe200_openers.parquet`, split
    by the gap between them. The published bar is a fixed 0.7, which does not
    travel between spaces, so the tail is read twice: at that bar, and at the
    bar where the FAR population has the same share above it as the published
    far population did (0.21%). The second is budget-matched and comparable.
    """
    frame = pd.read_parquet(DATA / "probe200_openers.parquet")
    frame = frame[frame.text.astype(str).str.strip() != ""].reset_index(drop=True)
    frame["when"] = pd.to_datetime(frame.ts, utc=True, errors="coerce")
    frame = frame.dropna(subset=["when"]).reset_index(drop=True)
    print(f"openers      : {len(frame):,} from {frame.hashed_ip.nunique():,} users")

    vectors = embed_all([str(t) for t in frame.text], kind)
    matrix = np.array([vectors[str(t)] for t in frame.text])

    near, far = [], []
    for _, rows in frame.groupby("hashed_ip", sort=False):
        if len(rows) < 2:
            continue
        index = rows.index.to_numpy()
        sims = matrix[index] @ matrix[index].T
        days = np.abs(rows.when.values[:, None] - rows.when.values[None, :]) / np.timedelta64(1, "D")
        upper = np.triu_indices(len(index), k=1)
        gap, cos = days[upper], sims[upper]
        near.extend(cos[gap <= 90].tolist())
        far.extend(cos[gap > 365].tolist())
    near, far = np.array(near), np.array(far)
    print(f"same-user    : {len(near):,} pairs within 90 days, {len(far):,} more than a year apart\n")

    mean_near, mean_far = float(near.mean()), float(far.mean())
    share_near = float((near >= 0.7).mean())
    share_far = float((far >= 0.7).mean())
    # Budget-matched: put the bar where the FAR population leaves 0.21% above it,
    # the share the published run measured at its own 0.7.
    bar = float(np.quantile(far, 1 - TAIL_PUBLISHED["share_far"]))
    matched_near = float((near >= bar).mean())

    print("                       within 90d    over 1 year     factor    published factor")
    print(f"  mean cosine          {mean_near:10.4f}  {mean_far:13.4f}  "
          f"{mean_near / mean_far:9.2f}  {TAIL_PUBLISHED['mean_factor']:17.2f}")
    print(f"  share >= 0.7 (fixed) {share_near:9.2%}  {share_far:13.2%}  "
          f"{(share_near / share_far if share_far else float('inf')):9.1f}  "
          f"{TAIL_PUBLISHED['tail_factor']:17.1f}")
    print(f"  share >= {bar:+.3f} (matched){matched_near:8.2%}  "
          f"{TAIL_PUBLISHED['share_far']:13.2%}  "
          f"{matched_near / TAIL_PUBLISHED['share_far']:9.1f}  "
          f"{TAIL_PUBLISHED['tail_factor']:17.1f}")
    print("\nThe finding is the CONTRAST between the two rows, not either level: a "
          "population aggregator reading means sees one number everywhere.")
    return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", default="onnx", choices=EMBEDDER_KINDS,
                        help="The vector space to re-embed in. `real` bills.")
    parser.add_argument("--figure", default="facet-boundary",
                        choices=("facet-boundary", "wildchat-spread", "tail-vs-mean"),
                        help="facet-boundary = docs/findings/facet-boundary-cost.md (§6); "
                             "wildchat-spread = docs/findings/real-users-ordering.md (§6b-bis); "
                             "tail-vs-mean = docs/findings/signal-in-the-tail.md (§4).")
    args = parser.parse_args()

    if args.figure == "wildchat-spread":
        return wildchat_spread(args.space)
    if args.figure == "tail-vs-mean":
        return tail_vs_mean(args.space)

    strict = pd.read_parquet(DATA / "intent_facets_strict_full.parquet")
    relaxed = pd.read_parquet(DATA / "intent_facets_relaxed_full.parquet")
    print(f"components   : {len(strict)} (strict) / {len(relaxed)} (relaxed), "
          f"two disjoint halves each")

    titles = [t for row in strict.itertuples() for t in list(row.a) + list(row.b)]
    facets = ([row.facet_a for row in strict.itertuples()]
              + [row.facet_b for row in strict.itertuples()]
              + [row.facet_a for row in relaxed.itertuples()]
              + [row.facet_b for row in relaxed.itertuples()])
    vectors = embed_all(titles + facets, args.space)

    methods = {
        "centroid": pairs_for(strict, vectors, "a", "b", centroid=True),
        "facet-strict": pairs_for(strict, vectors, "facet_a", "facet_b", centroid=False),
        "facet-relaxed": pairs_for(relaxed, vectors, "facet_a", "facet_b", centroid=False),
    }

    print()
    print("method".ljust(16) + "".join(f"@{b:.1%} FP".rjust(12) for b in BUDGETS)
          + "       AUC" + "   published @10.1%")
    for name, (positive, negative) in methods.items():
        recalls = recall_at_budgets(positive, negative)
        row = name.ljust(16) + "".join(f"{recalls[b]:11.1%} " for b in BUDGETS)
        print(row + f"{auc(positive, negative):10.4f}" + f"{PUBLISHED[name]:17.1%}")

    top = methods["centroid"][0], methods["centroid"][1]
    base = recall_at_budgets(*top)[BUDGETS[0]]
    print()
    for name in ("facet-strict", "facet-relaxed"):
        here = recall_at_budgets(*methods[name])[BUDGETS[0]]
        published_gap = (PUBLISHED["centroid"] - PUBLISHED[name]) * 100
        print(f"  {name:14s} {(base - here) * 100:5.1f} points below the centroid "
              f"(published, in bigquery:gemini-embedding-001:768: {published_gap:.1f})")
    print("\nThe GAP is what travels between spaces; the level is conditioned on the "
          "space, the generation and the corpus, and this corpus is Stack Overflow "
          "components under one frozen generation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
