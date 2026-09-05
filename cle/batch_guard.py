"""Guards against operations that return without working.

One failure family runs through the CLE: nothing raises, the numbers look
plausible, and the defect is only visible to someone reading the output closely.
A batch of model calls that all fail identically takes the same time as a batch
that all succeed. A cosine computed across two vector spaces returns a number in
[-1, 1] like any other. A proof of an event that never happened validates.

Three guards, all loud, all cheap:

  * `assert_batch_varied` — a batch whose outputs are all identical, or whose
    error share crosses a bar, is a failed batch even when every call returned.
  * `assert_unit_norm` — the CLE's `cosine` is a raw dot product and is a cosine
    only on unit vectors, so a vector whose norm is not 1 comes from a space the
    CLE does not compute in.
  * `assert_embeddable` — the only OUTBOUND guard. The other two, and every
    other check on the embedding path, inspect what comes back; without this one
    an empty opener is billed and then clustered as if it named an intent.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

#: Above this share of outputs carrying an error marker, the batch is refused.
#: Not 1.0: a batch that is mostly errors is a failed batch, and waiting for
#: *every* call to fail would let a 90%-broken run through.
MAX_ERROR_SHARE = 0.2

#: How far a norm may sit from 1 before it is refused. Loose enough for float32
#: round-trips through JSON, tight enough that BigQuery's 0.58 cannot pass.
NORM_TOLERANCE = 1e-3


class UniformBatchError(RuntimeError):
    """A batch returned, and returning is not the same as working.

    Raised when every output is identical, or when too many carry an error
    marker. Both shapes are indistinguishable from success by timing, by count,
    and by the absence of an exception — which is why they need a check of their
    own rather than a `try`.
    """


class UnnormalisedVectorError(ValueError):
    """A vector arrived with a norm that is not 1.

    The CLE's `cosine` is a raw dot product; it is a cosine only on unit
    vectors. Measured norms by source:

        HashedTokenEmbedder                1.000000
        CachedEmbedder                     1.000000
        RealEmbedder (calls `_l2`)         1.000000
        BigQuery `ML.GENERATE_EMBEDDING`   0.57 to 0.60

    The last figure is a range because it is a measurement, not a constant:
    min 0.572648, max 0.599283 over 20 vectors (`space_identity.py`). An earlier
    pass wrote "0.58 to 0.60", which excluded its own lower tail.

    The last one is not the CLE's space. `ML.GENERATE_EMBEDDING` runs
    `gemini-embedding-001`; the CLE runs `gemini-embedding-2`, on whichever
    surface serves it (AI Studio by key, or Vertex at `global` by
    application-default credentials: same vectors either way). Cosine between
    the two MODELS on the same texts is 0.040084,
    so what this guard refuses is a vector from a foreign space. The low norm is
    the symptom that can be checked cheaply, not the defect.

    RAISES rather than normalising silently, because normalising would hide the
    mismatch and produce a plausible number from an unrelated geometry. A caller
    holding BigQuery vectors should normalise at its own boundary, where the
    choice is visible, and know that normalising does not make them the CLE's
    vectors.
    """


class EmptyTextError(ValueError):
    """A text with no content was about to be embedded.

    Every other check on the embedding path inspects what comes back:
    `assert_batch_varied` the outputs, `assert_unit_norm` the vectors,
    `CacheMissError` the lookup. This one inspects what goes out, so an empty or
    whitespace-only opener never reaches the network, is never billed, and never
    enters clustering as an arbitrary point pretending to name an intent.

    The only guard on this path that prevents a call instead of diagnosing one.
    """


def assert_batch_varied(
    outputs: Sequence[str],
    *,
    label: str,
    error_marker: str = "__ERROR__",
    max_error_share: float = MAX_ERROR_SHARE,
) -> None:
    """Refuse a batch that returned without working."""
    if not outputs:
        return
    errors = sum(1 for o in outputs if isinstance(o, str) and o.startswith(error_marker))
    share = errors / len(outputs)
    if share > max_error_share:
        raise UniformBatchError(
            f"{label}: {errors}/{len(outputs)} outputs carry {error_marker!r} "
            f"({share:.0%} > {max_error_share:.0%}). A batch that returns is not "
            "a batch that worked: uniform failures and uniform successes take "
            "the same time and produce the same count."
        )
    if len(outputs) > 1 and len(set(outputs)) == 1:
        raise UniformBatchError(
            f"{label}: all {len(outputs)} outputs are identical. Either the input "
            "collapsed (gemini-embedding-2 treats a content list as ONE document) "
            "or every call failed the same way."
        )


def assert_unit_norm(vector: Sequence[float], *, where: str,
                     tolerance: float = NORM_TOLERANCE) -> None:
    """Refuse a vector whose norm is not 1. See `UnnormalisedVectorError`."""
    norm = math.sqrt(sum(float(x) * float(x) for x in vector))
    if norm == 0.0:
        return  # a zero vector is a documented "matches nothing", not a surface bug
    if abs(norm - 1.0) > tolerance:
        raise UnnormalisedVectorError(
            f"{where}: vector norm is {norm:.6f}, not 1 (tolerance {tolerance}). "
            "The CLE's `cosine` is a raw dot product and is a cosine only on unit "
            "vectors. Normalise at the boundary you control, explicitly."
        )


def assert_embeddable(text: str, *, where: str) -> None:
    """Refuse an empty text BEFORE the network. See `EmptyTextError`.

    The one guard on this path that fires outbound, so it is also the only one
    that prevents a billed call rather than diagnosing it afterwards.
    """
    if not isinstance(text, str) or not text.strip():
        raise EmptyTextError(
            f"{where}: refusing to embed an empty text ({text!r}). An empty opener "
            "is a defect upstream — in episode segmentation or in the corpus — and "
            "embedding it would put an arbitrary point into the clustering as if it "
            "named an intent."
        )
