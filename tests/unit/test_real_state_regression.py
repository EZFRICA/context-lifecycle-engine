"""The two real corpora as a non-regression reference.

`docs/FINDINGS.md` publishes numbers measured on Stack Overflow and WildChat.
This file recomputes them, so a change that moves one turns the suite red
instead of quietly making the documentation wrong.

OFFLINE AND FREE. Everything reads a pre-built vector cache: no network, no key,
no BigQuery.

SKIPPED ON A FRESH CLONE, deliberately. The corpora are gitignored, because
WildChat is real user text consented for research and the vector cache is 78 Mo.
These assertions therefore hold for whoever has the artifacts and vanish for
whoever does not, so the skip message names what is missing and how to rebuild
it rather than disappearing quietly.

SCOPE: bucket 2. The claims are about `google:gemini-embedding-2:768` at 0.775,
named in every assertion rather than assumed.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
STATES = ROOT / "examples/bigquery/states"
CACHE = ROOT / "examples/bigquery/data/vectors.corpus_states.json"
GROUND_TRUTH = STATES / "so_ground_truth.json"

REQUIRED = (STATES / "history_stackoverflow.jsonl", STATES / "history_wildchat.jsonl",
            CACHE, GROUND_TRUTH)

if not all(p.exists() for p in REQUIRED):
    pytest.skip(
        "the real corpora are not present (they are gitignored: real user text "
        "and a 78 Mo vector cache). Rebuild with "
        "examples/bigquery/prepare_states.py, which needs BigQuery. Missing: "
        + ", ".join(str(p.relative_to(ROOT)) for p in REQUIRED if not p.exists()),
        allow_module_level=True,
    )

from cle.detect.clusters import IntentClusterer, cluster_threshold_for  # noqa: E402
from cle.detect.embedders import CachedEmbedder  # noqa: E402
from cle.detect.episodes import (  # noqa: E402
    CoarseTimestampError,
    DetectorConfig,
    Message,
    segment,
)

CONFIG = DetectorConfig()
SPACE = "google:gemini-embedding-2:768"
THRESHOLD = 0.775


@pytest.fixture(scope="module")
def embedder():
    """The corpus cache, read by explicit path.

    NOT through `$CLE_VECTOR_CACHE`: that variable is process-wide, and setting
    it here would change which cache every other test in the session reads.
    """
    return CachedEmbedder.from_file(CACHE)


def _history(name: str) -> list[Message]:
    rows = [json.loads(line) for line in (STATES / f"history_{name}.jsonl").read_text().splitlines()]
    return [Message(text=r["text"], ts=r["ts"], thread_id=r["thread_id"],
                    user_id=r["user_id"]) for r in rows]


def _cluster(messages, embedder):
    episodes = segment(messages, CONFIG)
    clusterer = IntentClusterer(embedder, CONFIG)
    return episodes, [clusterer.assign(e) for e in episodes]


# ── the space itself ───────────────────────────────────────────────────────

def test_the_cache_is_the_space_the_published_figures_name(embedder) -> None:
    """Every figure below is conditioned on this, so it is asserted first.

    If the cache were regenerated in another space, the numbers underneath would
    change for a reason that has nothing to do with the detector, and the run
    would look like a detection regression.
    """
    assert embedder.embedder_id == SPACE
    assert cluster_threshold_for(embedder.embedder_id,
                                 CONFIG.cluster_similarity_threshold) == THRESHOLD


# ── Stack Overflow: detection against external ground truth ────────────────

def test_stackoverflow_segments_and_clusters_as_published(embedder) -> None:
    """`docs/FINDINGS.md` §1: "137 episodes, 60 clusters detected"."""
    messages = _history("stackoverflow")
    episodes, assignments = _cluster(messages, embedder)
    clusters = {a for a in assignments if a is not None}

    assert len(messages) == 137
    assert len(episodes) == 137, "every message is its own episode in this corpus"
    assert len(clusters) == 60, (
        f"60 clusters is the denominator of the ~2% random baseline; got {len(clusters)}"
    )


def test_the_detector_groups_two_thirds_of_moderator_attested_intents(embedder) -> None:
    """THE headline figure: two thirds of components grouped, vs ~2% at random.

    A component is a set of questions a Stack Overflow moderator closed as
    duplicates of one another: a human judgment the detector never sees. The
    measure asks whether the detector puts them in the same cluster.

    Both halves of the figure are asserted, because 67% alone is half a
    measurement: a detector collapsing everything into one cluster would score
    100% here. `false_trigger_rate` is the other half and is asserted in
    `test_frozen_defects` as the defect it is.
    """
    truth = json.loads(GROUND_TRUTH.read_text())
    messages = _history("stackoverflow")
    episodes, assignments = _cluster(messages, embedder)

    # component -> the clusters its episodes landed in
    landed: dict[str, list] = collections.defaultdict(list)
    for episode, assignment in zip(episodes, assignments):
        component = truth.get(episode.opener)
        if component is not None and assignment is not None:
            landed[component].append(assignment)

    present = {c: v for c, v in landed.items() if len(v) >= 2}
    grouped = {c: v for c, v in present.items() if len(set(v)) == 1}

    # Both the counts and the ratio are pinned. The counts are what THIS
    # reconstruction yields from the committed artifacts, which is what a reader
    # can check; the ratio is the finding, and it is exactly 2/3.
    assert (len(grouped), len(present)) == (32, 48), (
        f"got {len(grouped)}/{len(present)}, expected 32/48. A change here means "
        "the segmentation or the ground-truth join moved, not the detector"
    )
    assert len(grouped) / len(present) == pytest.approx(2 / 3, abs=0.005), (
        "the headline is the ratio: two thirds of moderator-attested intents "
        "land in one cluster, against ~2% at random"
    )


# ── WildChat: the population the engine can address ────────────────────────

def test_wildchat_cohort_and_the_coarse_timestamp_guard(embedder) -> None:
    """`docs/FINDINGS.md` §2: 29 of 40 users discarded by the timestamp guard.

    The guard is doing its job, not failing: those users carry one timestamp per
    conversation rather than per turn, so silence-based segmentation has nothing
    to segment. The number is published as the reason the addressable population
    is ~0.08% of the corpus, so it is pinned here.
    """
    messages = _history("wildchat")
    by_user: dict[str, list] = collections.defaultdict(list)
    for message in messages:
        by_user[message.user_id].append(message)

    discarded, episodes, sizes = 0, [], collections.Counter()
    for user, rows in sorted(by_user.items()):
        try:
            user_episodes, assignments = _cluster(rows, embedder)
        except CoarseTimestampError:
            discarded += 1
            continue
        episodes.extend(user_episodes)
        for assignment in assignments:
            if assignment is not None:
                sizes[(user, assignment)] += 1

    assert len(by_user) == 40
    assert discarded == 29, (
        f"the coarse-timestamp guard discarded {discarded}/40, expected 29. "
        "A change means max_zero_gap_share or the segmentation moved"
    )
    assert len(episodes) == 652
    assert sum(1 for n in sizes.values() if n >= 3) == 52
    assert sum(1 for n in sizes.values() if n >= 6) == 18
    assert sum(1 for n in sizes.values() if n >= 10) == 10


def test_the_occurrence_floor_is_visible_in_this_cohort(embedder) -> None:
    """`docs/FINDINGS.md` §3: the floor is occurrences per intent, not episodes.

    652 episodes across 11 segmentable users produce only 10 clusters at the
    reliable-recovery floor of 10 occurrences. Episode count predicts nothing,
    and this asserts the shape of that claim rather than restating it in prose.
    """
    messages = _history("wildchat")
    by_user: dict[str, list] = collections.defaultdict(list)
    for message in messages:
        by_user[message.user_id].append(message)

    total_episodes, at_ten = 0, 0
    for rows in by_user.values():
        try:
            episodes, assignments = _cluster(rows, embedder)
        except CoarseTimestampError:
            continue
        total_episodes += len(episodes)
        counts = collections.Counter(a for a in assignments if a is not None)
        at_ten += sum(1 for n in counts.values() if n >= 10)

    assert total_episodes > 600 and at_ten == 10, (
        f"{total_episodes} episodes yielded {at_ten} clusters at the >=10 floor; "
        "if episode count predicted recovery this ratio would not hold"
    )
