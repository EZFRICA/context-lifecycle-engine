"""Stability classifier properties IN THE `stub:hashed64` SPACE (hypothesis).

SCOPE — read before trusting the word "property". These are properties of the
v1 bag-of-tokens mechanism, **not** properties of the classifier in a semantic
embedding space. Hypothesis tests claim generality by their very format, and
two of the claims below are simply FALSE in the production space
(`google:gemini-embedding-2:768`), where the classifier returns
`verdict="unavailable"` and NO pair is ever divergent:

  * `test_same_flips_without_tool_flag_instability_iff_divergent` — the
    right-hand side stops holding: `unstable` is always False there.
  * `test_world_state_only_divergence_never_flags_unstable` — holds only where
    cosine separates the directives at all; in a semantic space it passes
    vacuously (nothing is divergent), which is not the guard being claimed.

Why they stay: they correctly pin the v1 mechanism, and the whole point of the
embedder run was to discover that cosine measures topical relatedness, not
contradiction (docs/METRICS.md). They must simply never be read as general
invariants of the classifier.
"""

import io
from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from cle.detect.clusters import HashedTokenEmbedder
from cle.detect.episodes import DetectorConfig, Message, segment
from cle.detect.stability import analyze_cluster_stability
from cle.oplog import OpLog

T0 = datetime(2026, 6, 1, tzinfo=timezone.utc)
CFG = DetectorConfig()
EMB = HashedTokenEmbedder()
EV = "schedule the monthly gdg meetup in the main room"
OK = "great confirm the main room booking and send the invites"
KO = "no room free find an alternative venue for the meetup evening"


def _eps(flips: list[bool], with_tool: bool = True):
    msgs = []
    for i, flip in enumerate(flips):
        th = f"e{i}"; ts = T0 + timedelta(days=2 * i)
        msgs.append(Message(user_id="u", ts=ts, text=EV, thread_id=th,
                            requires_tool="calendar_api" if with_tool else None,
                            tool_result=("no_slot" if flip else "slot_free") if with_tool else None))
        msgs.append(Message(user_id="u", ts=ts + timedelta(minutes=3),
                            text=KO if flip else OK, thread_id=th))
        msgs.append(Message(user_id="u", ts=ts + timedelta(minutes=6), text="thanks", thread_id=th))
    return segment(sorted(msgs, key=lambda m: m.ts), CFG)


def _run(eps):
    return analyze_cluster_stability(eps, EMB, CFG, OpLog(io.StringIO()), actor="t")


@settings(max_examples=20, deadline=None)
@given(st.lists(st.booleans(), min_size=2, max_size=6))
def test_classifier_is_deterministic(flips) -> None:
    # Scope: stub:hashed64. Determinism itself would hold in any space, but the
    # inputs it ranges over are only divergent under bag-of-tokens.
    eps = _eps(flips)
    assert _run(eps) == _run(eps)


@settings(max_examples=20, deadline=None)
@given(st.lists(st.booleans(), min_size=2, max_size=6), st.randoms())
def test_verdict_is_permutation_invariant(flips, rng) -> None:
    # Scope: stub:hashed64. In a semantic space every verdict is "unavailable",
    # so permutation invariance holds trivially and proves nothing.
    eps = _eps(flips)
    shuffled = list(eps); rng.shuffle(shuffled)
    a, b = _run(eps), _run(shuffled)
    assert a.unstable == b.unstable and a.counts == b.counts


@settings(max_examples=20, deadline=None)
@given(st.lists(st.booleans(), min_size=2, max_size=6))
def test_world_state_only_divergence_never_flags_unstable(flips) -> None:
    # Scope: stub:hashed64 ONLY. "Whatever the pattern, the anti-noise guard
    # holds" is true only where cosine separates the directives at all. In a
    # semantic space the planted OPPOSING directives score 0.62-0.86, nothing is
    # divergent, and this passes VACUOUSLY — not the guard being claimed.
    report = _run(_eps(flips, with_tool=True))
    assert report.counts["intra_cluster"] == 0
    assert not report.unstable


@settings(max_examples=20, deadline=None)
@given(st.lists(st.booleans(), min_size=2, max_size=6))
def test_same_flips_without_tool_flag_instability_iff_divergent(flips) -> None:
    # Scope: stub:hashed64 ONLY — this equivalence is FALSE in production.
    # Adjustment 2 as a property: strip the tool and the SAME textual divergence
    # becomes user signal — unstable exactly when both directives appear. Under
    # the real embedder the right-hand side still varies while `unstable` is
    # always False (nothing registers as divergent), so the iff breaks.
    report = _run(_eps(flips, with_tool=False))
    assert report.unstable == (len(set(flips)) > 1)
    assert report.counts["world_state"] == 0
