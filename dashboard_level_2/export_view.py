"""Export the cross-user clustering as a 2D view, one projection per method.

Writes `data/crossuser_view.json`, which `build.py` turns into the board. Runs
the same pipeline as `examples/bigquery/facet_crossuser_bench.py` - same
clusters, same facets, same space - and adds a PCA projection so the clusters can
be placed on a plane.

BILLS: one generation per cluster (46) and one embedding per distinct text (~97).
Cheap, but not free, which is why the JSON is committed: `build.py` alone needs
no cloud at all.

Paths resolve from the repository root, not the working directory, so this runs
from anywhere.
"""
import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

# The bench lives in examples/bigquery and imports `bqconfig` as a top-level
# module, so both that directory and the root have to be importable.
sys.path.insert(0, str(ROOT / "examples" / "bigquery"))
sys.path.insert(0, str(ROOT))

from facet_crossuser_bench import (  # noqa: E402
    embed, generate_facets, jaccard, load_clusters, redact,
)


def project(vec: dict[str, np.ndarray], texts: list[str]) -> tuple[np.ndarray, float]:
    """PCA to THREE dimensions, scaled into [-1, 1].

    Returns the coordinates and the share of variance the three axes carry. The
    share is exported and displayed because it is the honest caveat on the
    picture: even in three dimensions most of the structure of a 768-dimension
    space is not on the screen, and two points that look far apart may not be.
    A third axis buys back some of it, and the number says how much.
    """
    matrix = np.array([vec[t] for t in texts])
    matrix = matrix - matrix.mean(axis=0)
    _, singular, components = np.linalg.svd(matrix, full_matrices=False)
    xyz = matrix @ components[:3].T
    xyz = xyz / np.abs(xyz).max()
    return xyz, float((singular[:3] ** 2).sum() / (singular ** 2).sum())


def recall_at(pos: np.ndarray, neg: np.ndarray, fp: float) -> float:
    """Threshold so the non-matching pairs fire at `fp`, read on the matching ones."""
    return float((pos >= float(np.quantile(neg, 1 - fp))).mean())


def main() -> None:
    import itertools

    clusters = load_clusters()
    keys = sorted(clusters)
    facets = generate_facets(clusters)
    joined = {k: " ".join(v[:12]) for k, v in clusters.items()}
    redacted = {k: redact(v) for k, v in facets.items()}

    vec = embed(sorted(set(joined.values()) | set(facets.values()) | set(redacted.values())))

    views = {}
    for name, source in (("text", joined), ("facet", facets), ("facet-redacted", redacted)):
        present = [k for k in keys if k in source]
        xyz, variance = project(vec, [source[k] for k in present])
        views[name] = {
            "variance": round(variance, 3),
            "points": [
                {"user": u, "intent": i, "x": round(float(x), 4), "y": round(float(y), 4),
                 "z": round(float(z), 4), "facet": facets.get((u, i), ""),
                 "n": len(clusters[(u, i)])}
                for (u, i), (x, y, z) in zip(present, xyz)
            ],
        }

    pairs = [(a, b) for a, b in itertools.combinations(keys, 2) if a[0] != b[0]]
    scores = {}
    for name, source in (("text", joined), ("facet", facets), ("facet-redacted", redacted)):
        pos = np.array([float(np.dot(vec[source[a]], vec[source[b]]))
                        for a, b in pairs if a[1] == b[1]])
        neg = np.array([float(np.dot(vec[source[a]], vec[source[b]]))
                        for a, b in pairs if a[1] != b[1]])
        scores[name] = {str(fp): round(recall_at(pos, neg, fp) * 100, 1)
                        for fp in (0.101, 0.05, 0.01)}
    pos = np.array([jaccard(joined[a], joined[b]) for a, b in pairs if a[1] == b[1]])
    neg = np.array([jaccard(joined[a], joined[b]) for a, b in pairs if a[1] != b[1]])
    scores["text-jaccard"] = {str(fp): round(recall_at(pos, neg, fp) * 100, 1)
                              for fp in (0.101, 0.05, 0.01)}

    out = {
        "views": views,
        "scores": scores,
        "intents": sorted({i for _, i in keys}),
        "users": sorted({u for u, _ in keys}),
        "pairs": len(pairs),
        "positives": sum(1 for a, b in pairs if a[1] == b[1]),
    }
    target = HERE / "data" / "crossuser_view.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    print(f"  {len(keys)} clusters, {len(out['intents'])} intents, "
          f"{out['pairs']} cross-user pairs ({out['positives']} same-intent)")
    for name, row in scores.items():
        print(f"  {name:16} {row}")
    print(f"  -> {target.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
