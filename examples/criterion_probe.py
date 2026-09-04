"""Three candidate criteria for the floor, measured side by side.

None is a size threshold: size trades population against noise
directly, so the criterion has to be something else.

Declared BEFORE looking at results (task 2): the only combination that will be
tested is cohesion x capture, because they are the two that measure the cluster
itself rather than its schedule. No sweep over pairs.
"""
import collections
import itertools
import json
import statistics
import sys
from pathlib import Path

import numpy as np

EX = Path(__file__).resolve().parent
sys.path.insert(0, str(EX)); sys.path.insert(0, str(EX.parent))
from make_multiuser import BACKGROUND, planted_intent  # noqa: E402
from cle.detect.clusters import IntentClusterer, cluster_threshold_for  # noqa: E402
from cle.detect.embedders import open_embedder  # noqa: E402
from cle.detect.episodes import DetectorConfig, Message, segment  # noqa: E402

CFG = DetectorConfig()


def clusters(history: Path, embedder):
    recs = [json.loads(l) for l in history.read_text().splitlines()]
    msgs = [Message(**{k: r.get(k) for k in
                       ("text", "ts", "thread_id", "user_id", "requires_tool", "tool_result")})
            for r in recs]
    episodes = segment(msgs, CFG)
    cl = IntentClusterer(embedder, CFG)
    members = collections.defaultdict(list)
    for e in episodes:
        members[cl.assign(e)].append(e)
    return members, cl


def profile(group, centroid, threshold, embedder):
    """(cohesion_mean, cohesion_tail, regularity_cv, capture_rate)."""
    V = []
    for e in group:
        v = np.asarray(embedder.embed(e.opener), dtype=np.float64)
        n = np.linalg.norm(v)
        if n:
            V.append(v / n)
    sims = [float(a @ b) for a, b in itertools.combinations(V, 2)]
    coh_mean = statistics.mean(sims) if sims else 0.0
    coh_tail = (sum(1 for s in sims if s >= 0.8) / len(sims)) if sims else 0.0

    ts = sorted(e.messages[0].ts for e in group)
    gaps = [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    cv = (statistics.pstdev(gaps) / statistics.mean(gaps)
          if len(gaps) >= 2 and statistics.mean(gaps) else float("nan"))

    c = np.asarray(centroid, dtype=np.float64)
    cn = np.linalg.norm(c)
    capture = (sum(1 for v in V if float(v @ (c / cn)) >= threshold) / len(V)
               if len(V) and cn else 0.0)
    return coh_mean, coh_tail, cv, capture


def rows(histories, embedder, min_size=3):
    out = []
    threshold = cluster_threshold_for(getattr(embedder, "embedder_id", None),
                                      CFG.cluster_similarity_threshold)
    for h in histories:
        members, cl = clusters(h, embedder)
        for cid, group in members.items():
            if len(group) < min_size:
                continue
            maj = collections.Counter(
                planted_intent(e.messages[0].thread_id) for e in group).most_common(1)[0][0]
            m, t, cv, cap = profile(group, cl.centroids[cid], threshold, embedder)
            out.append({"kind": "fond" if maj in BACKGROUND else "tache",
                        "n": len(group), "coh": m, "tail": t, "cv": cv, "capture": cap})
    return out
