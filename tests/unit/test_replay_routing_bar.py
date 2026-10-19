"""The bar replay routes at belongs to the vector space, like every other one.

SCOPE: bucket 1 (embedder-agnostic). The embedder here is a local fake with a
fixed geometry: nothing real is embedded, and the point is the THRESHOLD
RESOLUTION, which is the same in every space.

CLE need. `replay_validate` compared each opener against
`config.cluster_similarity_threshold` raw - a 0.6 applied everywhere - while the
clustering half of the same build used `cluster_threshold_for(embedder_id, ...)`.
One build, one figure, two bars.

Measured consequence, on the Stack Overflow corpus in
`google:gemini-embedding-2:768`: the candidate grouped at its calibrated 0.775
and routed at 0.6, which sits BELOW that space's cross-intent median of 0.61.
76 of 131 out-of-cluster episodes fired, and the build published
`false_trigger_rate 0.580` - a number the repository has carried for months as a
measured defect OF THE DETECTOR. At the space's own bar the same trigger fires
on 0 of 131. The defect was the bar.

WHY IT SURVIVED, and why this file exists rather than a corpus test:
`stub:hashed64` is calibrated at 0.6, the same value the unscoped code used, so
the entire offline suite is blind to it. A guard that only runs in the space the
suite runs in could not have caught it and cannot protect the fix.
"""

import io
import math

import pytest

from cle.build.replay import replay_validate
from cle.detect.clusters import CLUSTER_THRESHOLD_BY_EMBEDDER
from cle.detect.episodes import DetectorConfig, Message
from cle.oplog import OpLog
from cle.store.commits import TriggerSpec

SPACE = "test:two-bars:2"

#: Cosine the planted off-cluster opener will have with the trigger centroid:
#: between the config default (0.6) and this space's calibrated bar (0.8), which
#: is the only region where the two rules disagree.
BETWEEN = 0.7


class _Fixed:
    """Returns a vector per text from a table; embeds nothing."""

    embedder_id = SPACE

    def __init__(self, table: dict[str, tuple[float, float]]) -> None:
        self._table = table

    def embed(self, text: str) -> tuple[float, float]:
        return self._table[text]


def _messages(texts: list[str]) -> list[Message]:
    """One message per DAY, so segmentation makes one episode of each: the
    silence rule is what forms episodes, and this test is not about it."""
    return [Message(text=text, ts=f"2026-01-{day:02d}T10:00:00+00:00",
                    thread_id=f"t{day}", user_id="u1")
            for day, text in enumerate(texts, start=1)]


def _vector_for(angle: float) -> tuple[float, float]:
    return (math.cos(angle), math.sin(angle))


@pytest.fixture
def space_calibrated_at_08(monkeypatch):
    monkeypatch.setitem(CLUSTER_THRESHOLD_BY_EMBEDDER, SPACE, 0.8)
    return SPACE


def _replay(embedder, messages):
    return replay_validate(
        trigger=TriggerSpec(centroid=(1.0, 0.0), embedder_id=SPACE),
        messages=messages,
        window_label="30d",
        existing_triggers=[],
        embedder=embedder,
        config=DetectorConfig(),
        oplog=OpLog(io.StringIO()),
        actor="test",
    ).pre_evidence


def test_an_opener_between_the_two_bars_does_not_fire(space_calibrated_at_08) -> None:
    """At 0.6 it fires and inflates `false_trigger_rate`; at the space's 0.8 it
    does not. This is the Stack Overflow 0.580 in miniature."""
    texts = ["in cluster one", "in cluster two", "unrelated"]
    table = {texts[0]: (1.0, 0.0), texts[1]: (1.0, 0.0),
             texts[2]: _vector_for(math.acos(BETWEEN))}

    evidence = _replay(_Fixed(table), _messages(texts))

    assert evidence.capture_rate == 1.0, "the in-cluster openers must still fire"
    assert evidence.false_trigger_rate == 0.0, (
        f"an opener at cosine {BETWEEN} fired against a space calibrated at 0.8: the "
        "routing bar has gone back to the unscoped config default"
    )


def test_the_bar_is_resolved_per_space_and_not_read_from_the_config(monkeypatch) -> None:
    """The negative control, white-box on purpose.

    With the fix, the routing bar IS the clustering bar, so an opener cannot be
    out-of-cluster and above the bar in a two-dimensional fixture: the geometry
    that would show it needs a corpus. What CAN be pinned here is the
    resolution itself - that replay asks the table for this space, rather than
    reading the config value the way it used to.
    """
    from cle.build import replay as replay_module

    asked: list[tuple] = []
    real = replay_module.cluster_threshold_for

    def spy(embedder_id, default):
        asked.append((embedder_id, default))
        return real(embedder_id, default)

    monkeypatch.setattr(replay_module, "cluster_threshold_for", spy)
    monkeypatch.setitem(CLUSTER_THRESHOLD_BY_EMBEDDER, SPACE, 0.8)
    texts = ["in cluster one", "in cluster two", "unrelated"]
    table = {texts[0]: (1.0, 0.0), texts[1]: (1.0, 0.0),
             texts[2]: _vector_for(math.acos(BETWEEN))}

    _replay(_Fixed(table), _messages(texts))

    assert (SPACE, DetectorConfig().cluster_similarity_threshold) in asked, (
        "replay did not resolve the bar for its own space; it is reading the "
        "unscoped config default again"
    )


def test_a_space_with_no_entry_falls_back_to_the_config_bar() -> None:
    """Unknown spaces keep the documented behaviour: the config value, which is
    also what `stub:hashed64` is calibrated at - the reason the suite was blind
    to the defect this file pins."""
    from cle.detect.clusters import cluster_threshold_for

    assert SPACE not in CLUSTER_THRESHOLD_BY_EMBEDDER
    default = DetectorConfig().cluster_similarity_threshold
    assert cluster_threshold_for(SPACE, default) == default
    assert CLUSTER_THRESHOLD_BY_EMBEDDER["stub:hashed64"] == default, (
        "the stub is calibrated at the config default; that coincidence is why "
        "an unscoped routing bar was invisible to the whole offline suite"
    )
