"""Shared GDG-fixture detection run (session-scoped: detect once, assert many).

The fixture is now realistic (varied phrasings), so the detector FRAGMENTS
each planted intent into many clusters — that is a measured finding, not a
bug. Tests therefore group episodes by the PLANTED intent (the thread prefix
in the committed .jsonl), never by a detected cluster. `planted_centroid`
gives the trigger centroid the detector WOULD use if the intent clustered
cleanly — the honest stand-in for a measurement that assumes recovery.
"""

import io
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from cle.detect.clusters import HashedTokenEmbedder, IntentClusterer, cosine
from cle.detect.episodes import DetectorConfig, Message, segment
from cle.oplog import OpLog

EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"


def _planted_intent(thread_id: str) -> str:
    return thread_id.split("-", 1)[0]


@pytest.fixture(scope="session")
def gdg():
    config = DetectorConfig()
    embedder = HashedTokenEmbedder()
    messages = [
        Message.model_validate(json.loads(l))
        for l in (EXAMPLES / "prompt_history_gdg.jsonl").read_text().splitlines() if l.strip()
    ]
    ground = json.loads((EXAMPLES / "gdg_ground_truth.json").read_text())
    episodes = segment(messages, config)

    # Detected clusters (for the recovery finding — how badly it fragments).
    clusterer = IntentClusterer(embedder, config)
    detected = [clusterer.assign(e) for e in episodes]
    by_cluster: dict[int, list] = {}
    for e, cid in zip(episodes, detected):
        by_cluster.setdefault(cid, []).append(e)

    # Planted grouping (the ground truth): episodes by their thread prefix.
    by_intent: dict[str, list] = {}
    for e in episodes:
        by_intent.setdefault(_planted_intent(e.messages[0].thread_id), []).append(e)

    def planted(intent: str) -> list:
        return sorted(by_intent[intent], key=lambda e: e.started_at)

    def planted_centroid(intent: str):
        # Normalized mean of the intent's opener embeddings — the trigger
        # centroid the detector WOULD use if the intent had clustered.
        vecs = [embedder.embed(e.opener) for e in by_intent[intent]]
        mean = [sum(col) / len(vecs) for col in zip(*vecs)]
        norm = math.sqrt(sum(v * v for v in mean)) or 1.0
        return tuple(v / norm for v in mean)

    def recovery(intent: str) -> tuple[int, int, int]:
        cids = {cid for e, cid in zip(episodes, detected)
                if _planted_intent(e.messages[0].thread_id) == intent}
        eps = by_intent[intent]
        return len(eps), len({e.opener for e in eps}), len(cids)

    return SimpleNamespace(
        config=config, messages=messages, ground=ground, episodes=episodes,
        by_cluster=by_cluster, centroids=clusterer.centroids, embedder=embedder,
        oplog=lambda: OpLog(io.StringIO()), cosine=cosine,
        planted=planted, planted_centroid=planted_centroid, recovery=recovery,
        planted_intents=ground["planted_intents"],
    )
