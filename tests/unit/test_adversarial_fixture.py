"""P1 arbitration: the adversarial fixture must yield a NON-trivial
false_trigger_rate — the demo may not only ever show 0.000.

Consumes the COMMITTED history artifacts (not the make_fixture generator), so
there is no import from examples/ (which a static analyzer can't resolve) and
the test runs on exactly the data that ships.
"""

import io
import json
from pathlib import Path

from cle.build.replay import replay_validate
from cle.detect.clusters import HashedTokenEmbedder, IntentClusterer
from cle.detect.episodes import DetectorConfig, Message, segment
from cle.oplog import OpLog
from cle.store.commits import TriggerSpec

EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"
RECAP_OPENER = "write the weekly recap of my project for the team"


def _load(name: str) -> list[Message]:
    return [
        Message.model_validate(json.loads(line))
        for line in (EXAMPLES / name).read_text().splitlines()
        if line.strip()
    ]


def _trigger_from_clean_history() -> TriggerSpec:
    # The candidate is detected on the CLEAN history (as the demo does); the
    # adversarial window is what replay then has to survive. The bridge is
    # engineered against the RECAP cluster specifically, so target that one by
    # its opener (the history now has several ritual clusters).
    config = DetectorConfig()
    episodes = segment(_load("prompt_history.jsonl"), config)
    clusterer = IntentClusterer(HashedTokenEmbedder(), config)
    assignments = [clusterer.assign(e) for e in episodes]
    recap_cluster = next(
        cid for e, cid in zip(episodes, assignments) if e.opener == RECAP_OPENER
    )
    return TriggerSpec(centroid=clusterer.centroids[recap_cluster])


def test_adversarial_window_produces_false_triggers() -> None:
    outcome = replay_validate(
        trigger=_trigger_from_clean_history(),
        messages=_load("prompt_history_adversarial.jsonl"),
        window_label="35d",
        existing_triggers=[],
        embedder=HashedTokenEmbedder(),
        config=DetectorConfig(),
        oplog=OpLog(io.StringIO()),
        actor="human:test",
    )
    assert outcome.pre_evidence.false_trigger_rate > 0.0
    assert outcome.pre_evidence.capture_rate == 1.0
