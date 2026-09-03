"""The detection vector space is selected at ONE point.

SCOPE — bucket 2 (stub-as-a-tool): the assertions are about which embedder the
selection point returns, never about any vector space's behaviour.

CLE need. A hardcoded `_configured_embedder()` returning `HashedTokenEmbedder()`
hardcoded, so no CLI invocation could run detection on the real embedding space
— the one the operator chose and the one `cluster_threshold_for` is calibrated
against. "Real tests" could therefore only ever mean the fingerprinter.

The selection point mirrors `open_store` deliberately: one factory, an env var
the CLI sets once in its callback, and a loud failure on an unknown kind. Two
commands in one session detecting in different spaces would write centroids that
cannot be compared into one topology claiming one embedding config.

NO LIVE CALL IS MADE HERE. `open_embedder("real")` constructs `RealEmbedder`,
which needs a key and the network, so it is exercised through a monkeypatched
attribute — never imported (the import ban in test_embedder_provenance still
holds; this module does not import it).
"""

import pytest

from cle.detect import embedders
from cle.detect.embedders import EMBEDDER_KINDS, open_embedder


def test_the_default_is_the_stub_so_existing_histories_keep_working() -> None:
    # NOT "cached", even though cached vectors are better: every topology
    # written so far records stub:hashed64, and silently switching would make
    # the next write assert a vector space the history was not produced in.
    assert open_embedder().embedder_id == "stub:hashed64"


def test_cached_is_the_real_geometry_offline() -> None:
    assert open_embedder("cached").embedder_id == "google:gemini-embedding-2:768"


def test_the_env_var_selects_and_the_argument_wins_over_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLE_EMBEDDER", "cached")
    assert open_embedder().embedder_id == "google:gemini-embedding-2:768"
    # An explicit argument overrides the ambient setting — the CLI callback
    # relies on this ordering.
    assert open_embedder("stub").embedder_id == "stub:hashed64"


def test_an_unknown_kind_raises_rather_than_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A silent fallback to the stub would run detection in the WRONG space
    # while the topology recorded whatever the caller believed it asked for.
    with pytest.raises(ValueError, match="unknown embedder kind"):
        open_embedder("gemini")
    monkeypatch.setenv("CLE_EMBEDDER", "typo")
    with pytest.raises(ValueError, match="unknown embedder kind"):
        open_embedder()


def test_real_reaches_the_live_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    """`real` must construct the live one — checked without a network call.

    If this ever silently returned the cache, a run believed to be live would
    be reading frozen vectors, and the bill would be the only way to tell.
    """
    built = []

    class FakeLive:
        embedder_id = "google:gemini-embedding-2:768"

        def __init__(self) -> None:
            built.append(True)

    monkeypatch.setattr(embedders, "RealEmbedder", FakeLive)
    assert open_embedder("real").embedder_id == "google:gemini-embedding-2:768"
    assert built == [True], "open_embedder('real') did not construct the live embedder"


def test_every_kind_is_reachable_and_the_list_is_not_stale() -> None:
    # A kind named in EMBEDDER_KINDS that the factory rejects would be a name
    # designating nothing — the pattern this codebase keeps reproducing.
    for kind in EMBEDDER_KINDS:
        if kind == "real":
            continue  # covered above without touching the network
        assert open_embedder(kind) is not None
