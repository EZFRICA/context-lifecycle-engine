"""Two of the three silent-failure guards.

The third, `assert_embeddable`, is tested in
`tests/unit/test_vector_contract_bites.py`. It is the only one that fires
OUTBOUND: these two check what came back, so an empty opener used to be billed
and then clustered as if it named an intent.

SCOPE — bucket 1 (embedder-agnostic): no vector space is under test, only the
shape of a failure.

CLE need. Both guards catch one failure family: nothing raises, the numbers look
right, and the defect survives until someone reads the output closely. A
fabricated `Persistence`; a stale centroid compared across two spaces; and the
case these were written for, a batch of 52 model calls that all failed with
`AttributeError` in 0.8 s each and was reported as 52 successes.

**At the level of timing, 52 uniform failures and 52 uniform successes are the
same observation.** That is why a check is needed rather than a `try`.
"""

import pytest

from cle.batch_guard import (
    UniformBatchError,
    UnnormalisedVectorError,
    assert_batch_varied,
    assert_unit_norm,
)


# ── the uniform-batch guard ─────────────────────────────────────────────────

def test_a_batch_of_uniform_errors_is_refused() -> None:
    # The observed shape: every call returned, every one carried the marker.
    outputs = ["__ERROR__ AttributeError"] * 52
    with pytest.raises(UniformBatchError, match="52/52"):
        assert_batch_varied(outputs, label="pilote")


def test_a_minority_of_errors_is_tolerated() -> None:
    # A real batch has stragglers. Refusing on the first failure would make the
    # guard something people disable.
    outputs = ["fine"] * 19 + ["__ERROR__ Timeout"]
    assert_batch_varied(outputs, label="pilote") is None


def test_a_majority_of_errors_is_refused_even_when_some_worked() -> None:
    # Waiting for EVERY call to fail would let a 90%-broken run through.
    outputs = ["fine"] * 3 + ["__ERROR__ Timeout"] * 17
    with pytest.raises(UniformBatchError, match="85%"):
        assert_batch_varied(outputs, label="pilote")


def test_identical_outputs_are_refused_even_without_an_error_marker() -> None:
    """The batching collapse, which raises nothing at all.

    `gemini-embedding-2` treats a list of contents as ONE multi-part document,
    so passing 190 texts as one list returns a single vector. Nothing raises;
    the only visible symptom is a 34 KB file where megabytes were expected.
    """
    with pytest.raises(UniformBatchError, match="identical"):
        assert_batch_varied(["same"] * 10, label="embed_many")


def test_a_varied_batch_passes() -> None:
    # Guards the guard: a check that refused everything would pass every test
    # above on its own.
    assert assert_batch_varied(["a", "b", "c"], label="pilote") is None
    assert assert_batch_varied([], label="pilote") is None
    assert assert_batch_varied(["only one"], label="pilote") is None


# ── the norm guard ──────────────────────────────────────────────────────────

def test_a_bigquery_shaped_norm_is_refused() -> None:
    """0.5868 is the measured norm of a BigQuery vector.

    `RealEmbedder` calls `_l2` and returns 1.0; `ML.GENERATE_EMBEDDING` does not
    renormalise after the Matryoshka truncation and returns 0.58 to 0.60.

    Those are not two views of one model. The CLE runs `gemini-embedding-2`;
    `ML.GENERATE_EMBEDDING` runs `gemini-embedding-001`. Measured: the committed
    cache reproduces against `gemini-embedding-2` at 1.000000 (on either surface
    that serves it, AI Studio or Vertex) and against `gemini-embedding-001` at
    0.040084.

    So what this guard refuses is a vector from a FOREIGN SPACE, which is a
    stronger thing to refuse than an unnormalised copy of the same one. The norm
    is the symptom the check can see cheaply, not the defect itself. See
    `cle/batch_guard.py` and `docs/FINDINGS.md`.
    """
    vector = [0.5868] + [0.0] * 767
    with pytest.raises(UnnormalisedVectorError, match="0.5868"):
        assert_unit_norm(vector, where="BigQuery")


def test_a_unit_vector_passes() -> None:
    assert assert_unit_norm([1.0, 0.0, 0.0], where="cache") is None
    assert assert_unit_norm([0.6, 0.8], where="cache") is None


def test_a_zero_vector_is_allowed() -> None:
    # Documented behaviour, not an oversight: `cosine` says a zero vector
    # matches nothing. Refusing it here would turn a defined case into an error.
    assert assert_unit_norm([0.0, 0.0, 0.0], where="cache") is None


def test_the_shipped_cache_passes_its_own_boundary_check() -> None:
    """The guard runs on every `CachedEmbedder.from_file`, so this asserts the
    committed cache is what the CLE thinks it is, and would fail loudly if it
    were ever regenerated in a space whose vectors are not unit length, such as
    `bigquery:gemini-embedding-001:768`."""
    from cle.detect.embedders import CachedEmbedder

    assert CachedEmbedder.from_file() is not None
