"""P1 arbitration: the adversarial fixture must yield a NON-trivial
false_trigger_rate — the demo may not only ever show 0.000."""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "examples"))

from make_fixture import adversarial_history, synthetic_history

from cle.build.replay import replay_validate
from cle.detect.clusters import HashedTokenEmbedder, IntentClusterer
from cle.detect.episodes import DetectorConfig, segment
from cle.oplog import OpLog
from cle.store.commits import TriggerSpec


def _trigger_from_clean_history() -> TriggerSpec:
    # The candidate is detected on the CLEAN history (as the demo does);
    # the adversarial window is what replay then has to survive.
    config = DetectorConfig()
    episodes = segment(synthetic_history(), config)
    clusterer = IntentClusterer(HashedTokenEmbedder(), config)
    assignments = [clusterer.assign(e) for e in episodes]
    recap_cluster = max(set(assignments), key=assignments.count)
    return TriggerSpec(centroid=clusterer.centroids[recap_cluster])


def test_adversarial_window_produces_false_triggers() -> None:
    outcome = replay_validate(
        trigger=_trigger_from_clean_history(),
        messages=adversarial_history(),
        window_label="35d",
        existing_triggers=[],
        embedder=HashedTokenEmbedder(),
        config=DetectorConfig(),
        oplog=OpLog(io.StringIO()),
        actor="human:test",
    )
    assert outcome.pre_evidence.false_trigger_rate > 0.0
    assert outcome.pre_evidence.capture_rate == 1.0
