"""Export the level 2 view from REAL users, not the synthetic fixture.

`export_view.py` runs on `make_multiuser.py`'s 12 synthetic users, which exist
because they carry ground truth: two users sharing a planted intent is a known
positive, so recall can be measured. Real users carry no such labels.

So the two exports answer two different questions and the board shows both:

    export_view.py   synthetic, labelled   -> the MEASUREMENT (recall at a budget)
    export_real.py   real, unlabelled      -> what level 2 actually SEES

This one is the second. It takes the 130 clusters that `make_facets.py` produced
from 40 real WildChat users - real prompts, real episodes, real generated facets
- and projects them the same way, so the plot on the board is real data even
where the recall table cannot be.

WHAT CANNOT BE COMPUTED HERE, and is therefore absent rather than estimated:
recall, precision, or any figure needing a label. Nobody has said which two real
users share an intent, and inventing that answer is the failure this project
keeps guarding against. What IS computed is the similarity distribution: how
close real cross-user clusters actually get, which is what decides whether a
population layer would surface anything at all.

BILLS: one embedding per distinct text (~390). No generation - the facets were
generated once and are committed.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "examples" / "bigquery"))
sys.path.insert(0, str(ROOT))

from cle.population.leak import redact  # noqa: E402
from cle.population.lexical import jaccard  # noqa: E402

SOURCE = ROOT / "examples" / "bigquery" / "data" / "facets_probe200_40.parquet"


def project(vec, texts):
    """PCA to three dimensions, scaled into [-1, 1]; returns coords and variance kept."""
    matrix = np.array([vec[t] for t in texts])
    matrix = matrix - matrix.mean(axis=0)
    _, singular, components = np.linalg.svd(matrix, full_matrices=False)
    xyz = matrix @ components[:3].T
    return xyz / np.abs(xyz).max(), float((singular[:3] ** 2).sum() / (singular ** 2).sum())


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(
            f"{SOURCE} is missing. It is gitignored WildChat material; regenerate "
            "with examples/bigquery/make_facets.py, which bills."
        )
    # Imported here, after the refusal: importing it builds nothing, but the
    # embedding it provides bills, and nothing before this line needs it.
    from facet_crossuser_bench import embed

    frame = pd.read_parquet(SOURCE)
    frame = frame[frame.facet.astype(str).str.strip() != ""].reset_index(drop=True)

    # An episode column is an array of raw prompts. Joined here for embedding and
    # for the text baseline; NEVER written to the export, which carries facets
    # only. This file is the one place real user text is read, and it does not
    # leave the process.
    joined = [" ".join(map(str, e))[:4000] for e in frame.episodes]
    facets = list(frame.facet)
    redacted = [redact(f) for f in facets]

    vec = embed(sorted(set(joined) | set(facets) | set(redacted)))

    views = {}
    for name, texts in (("text", joined), ("facet", facets), ("facet-redacted", redacted)):
        xyz, variance = project(vec, texts)
        views[name] = {
            "variance": round(variance, 3),
            "points": [
                # `user` is already a hash in the corpus; truncated further so the
                # export cannot be joined back to the cohort file.
                {"user": u[:8], "intent": "", "x": round(float(x), 4),
                 "y": round(float(y), 4), "z": round(float(z), 4),
                 "facet": f, "n": int(n)}
                for u, n, f, (x, y, z) in zip(frame.user, frame.n, facets, xyz)
            ],
        }

    # No labels, so no recall. What can be said is how close cross-user pairs get.
    pairs = [(i, j) for i in range(len(frame)) for j in range(i + 1, len(frame))
             if frame.user[i] != frame.user[j]]
    spread = {}
    for name, texts in (("text", joined), ("facet", facets), ("facet-redacted", redacted)):
        sims = np.array([float(np.dot(vec[texts[i]], vec[texts[j]])) for i, j in pairs])
        spread[name] = {
            "pairs": len(pairs),
            "median": round(float(np.median(sims)), 4),
            "p95": round(float(np.quantile(sims, 0.95)), 4),
            "p99": round(float(np.quantile(sims, 0.99)), 4),
            "above_0_7": int((sims >= 0.7).sum()),
            "above_0_8": int((sims >= 0.8).sum()),
        }
    sims = np.array([jaccard(joined[i], joined[j]) for i, j in pairs])
    spread["text-jaccard"] = {
        "pairs": len(pairs), "median": round(float(np.median(sims)), 4),
        "p95": round(float(np.quantile(sims, 0.95)), 4),
        "p99": round(float(np.quantile(sims, 0.99)), 4),
        "above_0_7": int((sims >= 0.7).sum()), "above_0_8": int((sims >= 0.8).sum()),
    }

    out = {
        "source": "WildChat, 40 real users, 130 clusters, facets generated once",
        "labelled": False,
        "views": views,
        "spread": spread,
        "users": frame.user.nunique(),
        "clusters": len(frame),
    }
    target = HERE / "data" / "real_view.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    print(f"  {len(frame)} real clusters from {frame.user.nunique()} real users")
    print(f"  cross-user pairs: {len(pairs):,}")
    for name, row in spread.items():
        print(f"  {name:16} median {row['median']:+.3f}  p99 {row['p99']:+.3f}  "
              f">=0.7: {row['above_0_7']:,}  >=0.8: {row['above_0_8']:,}")
    print(f"  -> {target.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
