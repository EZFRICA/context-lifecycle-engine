"""The vector contract, enforced rather than described.

An exception class appearing in a test file says nothing about which of its
raise sites is covered. Three guards on this path are easy to believe are tested
and are not, unless something asserts them directly:

  * `DimensionMismatchError` in `cosine`. One raise site, and the contract it
    enforces is described at length in `docs/TESTING.md`, which is not a test.
  * `SpaceMismatchError` at the two REPLAY sites. A third site lives in
    `commits.py` and is covered by `test_embedder_provenance`, which makes the
    exception look tested while two of its three sites are free.
  * `EmptyTextError`, the outbound guard on the embedding path.

`python tools/mutate.py` is how this is checked rather than assumed.
"""

from __future__ import annotations

import io

import pytest

from cle.batch_guard import EmptyTextError, assert_embeddable
from cle.detect.clusters import DimensionMismatchError, cosine
from cle.detect.embedders import CachedEmbedder, SpaceMismatchError, StubEmbedder
from cle.oplog import OpLog
from cle.store.backends import InMemoryStore

from tests.unit.test_runtime import _build_image


def test_cosine_refuses_two_lengths(tmp_path) -> None:
    """`zip` used to truncate to the shorter vector and return a real number.

    A 64-d stub centroid against a 768-d real embedding returned -0.012148 and
    raised nothing, which is why the guard exists. Nothing tested it.
    """
    with pytest.raises(DimensionMismatchError):
        cosine((1.0, 0.0, 0.0), (1.0, 0.0))


def test_cosine_still_works_on_equal_lengths() -> None:
    # The negative, so the guard cannot be "fixed" by raising on everything.
    assert cosine((1.0, 0.0), (1.0, 0.0)) == pytest.approx(1.0)
    assert cosine((1.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)


def test_replay_refuses_an_embedder_from_another_space() -> None:
    """The entry check at `replay.py:146`, which no test exercised.

    Guarding on IDENTITY rather than dimension is the whole point: the stub is
    64-d and the cache 768-d here, but two distinct real spaces of equal width
    would pass a length check and mean nothing.
    """
    from cle.build.replay import replay_validate
    from cle.detect.episodes import DetectorConfig, Message

    store = InMemoryStore()
    oplog = OpLog(io.StringIO())
    image = _build_image(store, oplog)          # its trigger is stub:hashed64
    assert image.trigger.embedder_id == StubEmbedder().embedder_id

    foreign = CachedEmbedder.from_file()
    assert foreign.embedder_id != image.trigger.embedder_id

    messages = [
        Message(text="prepare the weekly roundup", ts="2026-04-01T09:00:00+00:00",
                thread_id="t0", user_id="u"),
        Message(text="prepare the weekly roundup again", ts="2026-04-08T09:00:00+00:00",
                thread_id="t1", user_id="u"),
    ]
    with pytest.raises(SpaceMismatchError):
        replay_validate(
            trigger=image.trigger, messages=messages, window_label="40d",
            existing_triggers=[], embedder=foreign, config=DetectorConfig(),
            oplog=oplog, actor="human:test",
        )


def test_the_operand_check_reads_the_operand_not_the_caller() -> None:
    """The per-operand check at `replay.py:79`.

    Distinct from the entry check above: that one reads the embedder handed in,
    this one reads the provenance of the vector actually being compared, so it
    survives a centroid entering by a path the entry check never sees.
    """
    from cle.build.replay import _require_operand_space
    from cle.store.commits import TriggerSpec

    trigger = TriggerSpec(centroid=(1.0, 0.0), embedder_id="stub:hashed64")
    _require_operand_space("stub:hashed64", trigger, what="an operand")  # no raise
    with pytest.raises(SpaceMismatchError):
        _require_operand_space("google:gemini-embedding-2:768", trigger,
                               what="a foreign operand")


@pytest.mark.parametrize("text", ["", "   ", "\n\t", None])
def test_an_empty_text_is_refused_before_the_network(text) -> None:
    """The outbound guard. See the module docstring."""
    with pytest.raises(EmptyTextError):
        assert_embeddable(text, where="test")


def test_a_real_text_still_passes() -> None:
    assert_embeddable("prepare the weekly roundup", where="test") is None


def test_the_cached_embedder_refuses_an_empty_opener() -> None:
    """Wired, not just defined: an empty opener must not reach the lookup.

    Without this the failure surfaces as `CacheMissError`, which names the wrong
    defect and sends the reader to regenerate a cache that is not the problem.
    """
    with pytest.raises(EmptyTextError):
        CachedEmbedder.from_file().embed("  ")


def test_an_embedding_response_with_no_vector_is_refused() -> None:
    """The call succeeded and carried nothing back.

    The SDK types both `embeddings` and `.values` as optional, and a filtered or
    truncated response fills neither. Without this guard the failure is a
    `NoneType` attribute error a frame or two from the call, naming nothing.

    Tests `vector_from_response`, the pure reader, rather than the embedder that
    calls it: no test module may import the live embedder, and that ban has its
    own test.
    """
    from cle.detect.embedders import EmptyEmbeddingError, vector_from_response

    class _Response:
        def __init__(self, embeddings):
            self.embeddings = embeddings

    class _Vectorless:
        values = None

    for empty in (None, [], [_Vectorless()]):
        with pytest.raises(EmptyEmbeddingError):
            vector_from_response(_Response(empty), "a real opener")


def test_a_populated_embedding_response_is_read() -> None:
    """The negative: a guard that refused everything would pass the test above."""
    from cle.detect.embedders import vector_from_response

    class _Embedding:
        values = [0.0, 1.0, 0.0]

    class _Response:
        embeddings = [_Embedding()]

    assert vector_from_response(_Response(), "a real opener") == [0.0, 1.0, 0.0]
