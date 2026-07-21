"""Shared GDG-fixture detection run (session-scoped: detect once, assert many)."""

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cle.detect.clusters import HashedTokenEmbedder, IntentClusterer
from cle.detect.episodes import DetectorConfig, Message, segment
from cle.oplog import OpLog

EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"


@pytest.fixture(scope="session")
def gdg():
    config = DetectorConfig()
    messages = [
        Message.model_validate(json.loads(l))
        for l in (EXAMPLES / "prompt_history_gdg.jsonl").read_text().splitlines() if l.strip()
    ]
    ground = json.loads((EXAMPLES / "gdg_ground_truth.json").read_text())
    episodes = segment(messages, config)
    clusterer = IntentClusterer(HashedTokenEmbedder(), config)
    by_cluster: dict[int, list] = {}
    for e in episodes:
        by_cluster.setdefault(clusterer.assign(e), []).append(e)

    def cluster_of(opener: str):
        for cid, eps in by_cluster.items():
            if any(x.opener == opener for x in eps):
                return cid, eps
        raise KeyError(opener)

    return SimpleNamespace(
        config=config, messages=messages, ground=ground, episodes=episodes,
        by_cluster=by_cluster, centroids=clusterer.centroids, cluster_of=cluster_of,
        embedder=HashedTokenEmbedder(), oplog=lambda: OpLog(io.StringIO()),
    )
