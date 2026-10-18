"""The space bench's labels and metrics (`examples/onnx_embedding_bench.py`).

SCOPE: bucket 1 (embedder-agnostic). Nothing here embeds a text: the bench's
candidate space is a 622 MB ONNX file the suite never downloads, and what is
under test is the part that would be wrong without it being obvious - which
openers carry which label, and what the two scores do.

CLE need. The bench's first run reported 44 openers and 4 planted intents, and
nothing failed: it had read `labeled_threads` from the ground-truth sidecar as
the intent, when that field carries a CONFLICT kind (`world_state`,
`intra_cluster`) for the contradiction taxonomy. Three of the seven planted
intents were silently dropped and the measurement ran on half the corpus. A
figure published from that run would have been wrong in a way no reader could
have detected, so the label extraction has a test and the sidecar's own count is
the authority.
"""

import json
import pathlib

import pytest

from onnx_embedding_bench import (
    GROUND_TRUTH,
    HOLDOUT_NOISE,
    adjusted_rand,
    openers_with_intents,
    purity_completeness,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


# ── the labels ──────────────────────────────────────────────────────────────

def test_every_planted_gdg_intent_reaches_the_bench() -> None:
    """The regression above: seven are planted, seven must arrive."""
    planted = set(json.loads(GROUND_TRUTH.read_text())["planted_intents"])
    pairs = openers_with_intents("gdg")
    assert {intent for _, intent in pairs} == planted
    # And the corpus is not quietly halved: the engine segments 246 episodes out
    # of this fixture, of which the planted threads are the clear majority.
    assert len(pairs) > 70


def test_the_holdout_keeps_its_patterns_and_drops_its_noise() -> None:
    """`make_holdout.py` plants three patterns; noise is not an intent."""
    intents = {intent for _, intent in openers_with_intents("holdout")}
    assert intents == {"venue", "meetup", "outreach"}
    assert HOLDOUT_NOISE not in intents


def test_an_unknown_corpus_is_refused_rather_than_defaulted() -> None:
    with pytest.raises((SystemExit, KeyError, ValueError)):
        openers_with_intents("wildchat")


# ── the metrics ─────────────────────────────────────────────────────────────

def test_purity_alone_rewards_shattering_a_corpus() -> None:
    """One opener per cluster is perfectly pure and says nothing - which is why
    the bench never reports purity without completeness."""
    intents = ["a", "a", "b", "b"]
    purity, completeness = purity_completeness([0, 1, 2, 3], intents)
    assert purity == 1.0
    assert completeness == 0.5


def test_completeness_alone_rewards_collapsing_it() -> None:
    intents = ["a", "a", "b", "b"]
    purity, completeness = purity_completeness([0, 0, 0, 0], intents)
    assert completeness == 1.0
    assert purity == 0.5


def test_a_perfect_grouping_scores_one_on_both() -> None:
    purity, completeness = purity_completeness([0, 0, 1, 1], ["a", "a", "b", "b"])
    assert (purity, completeness) == (1.0, 1.0)


def test_the_agreement_index_is_one_on_a_relabelling_not_on_a_reshuffle() -> None:
    """Cluster ids are arbitrary, so agreement must survive renaming them and
    must not survive regrouping the items."""
    assert adjusted_rand([0, 0, 1, 1], [7, 7, 3, 3]) == pytest.approx(1.0)
    assert adjusted_rand([0, 0, 1, 1], [0, 1, 0, 1]) < 0.1


def test_the_agreement_index_is_defined_when_both_sides_are_one_cluster() -> None:
    """The degenerate case the formula divides by zero on; the bench prints this
    value at low thresholds, where every space collapses."""
    assert adjusted_rand([0, 0, 0], [0, 0, 0]) == pytest.approx(1.0)
