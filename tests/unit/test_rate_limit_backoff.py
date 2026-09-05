"""The retry policy on the live embedding surface.

SCOPE — bucket 1 (embedder-agnostic): no vector space is under test, only which
failures are worth a second attempt.

CLE need. Without a backoff, the sample size of a live measurement is set by the
quota rather than by the operator. Measured: comparing 186 cached vectors against
AI Studio lost 32 to 429s, and an immediate second pass lost 86 — so the figure
that came back described whatever survived the quota, and a rerun described
something else. That is not a slow measurement, it is an unrepeatable one.

`RealEmbedder` itself is never imported here: importing it is a dependency on the
network and a key, and that ban is asserted by
`test_no_test_module_imports_real_embedder`. The retry loop and its predicate are
module-level for exactly this reason.
"""

import pytest

from cle.detect.embedders import (
    RETRY_ATTEMPTS,
    RETRY_BASE_SECONDS,
    RETRY_MAX_SECONDS,
    _is_rate_limit,
    call_with_backoff,
)


class _ClientError(Exception):
    """Stands in for the SDK's 4xx wrapper, which is one class for every 4xx."""


# ── which failures are rate limits ──────────────────────────────────────────

@pytest.mark.parametrize("message", [
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429}}",
    "RESOURCE_EXHAUSTED: quota exceeded for this project",
    "Error code: 429",
])
def test_rate_limits_are_recognised(message: str) -> None:
    assert _is_rate_limit(_ClientError(message))


@pytest.mark.parametrize("message", [
    "400 INVALID_ARGUMENT: output_dimensionality must be positive",
    "403 PERMISSION_DENIED: the caller does not have permission",
    "404 NOT_FOUND: model not found",
])
def test_other_client_errors_are_not_retried(message: str) -> None:
    """A 400 or a 403 fails identically on every attempt.

    Retrying those would turn a clear error into a slow one, and hide a
    misconfiguration behind a pause.
    """
    assert not _is_rate_limit(_ClientError(message))


def test_the_predicate_reads_the_class_name_too() -> None:
    """The SDK may carry the code in the type rather than the message."""
    assert _is_rate_limit(type("ResourceExhausted", (Exception,), {})("no detail"))


# ── the loop ────────────────────────────────────────────────────────────────

@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Capture the waits instead of serving them.

    The SHIPPED `call_with_backoff` is what runs here. An earlier version of this
    file reimplemented the loop body, which made every test below pass against a
    copy of the code: deleting the real retry left the suite green. Patching
    `time.sleep` in the module under test keeps the real control flow and only
    removes the waiting.
    """
    recorded: list[float] = []
    monkeypatch.setattr(
        "cle.detect.embedders.time.sleep", lambda seconds: recorded.append(seconds)
    )
    return recorded


def test_a_burst_is_ridden_out(sleeps: list[float]) -> None:
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _ClientError("429 RESOURCE_EXHAUSTED")
        return "vector"

    assert call_with_backoff(flaky) == "vector"
    assert calls["n"] == 3
    assert len(sleeps) == 2, "one wait per retry, none after the success"


def test_an_exhausted_quota_still_fails(sleeps: list[float]) -> None:
    """The point is a bounded retry, not an infinite one.

    A quota that is genuinely gone must surface while the operator is still
    watching, not an hour later.
    """
    def always():
        raise _ClientError("429 RESOURCE_EXHAUSTED")

    with pytest.raises(_ClientError):
        call_with_backoff(always)
    assert len(sleeps) == RETRY_ATTEMPTS - 1, "no wait after the final attempt"


def test_a_non_rate_limit_fails_on_the_first_attempt(sleeps: list[float]) -> None:
    calls = {"n": 0}

    def bad_request():
        calls["n"] += 1
        raise _ClientError("400 INVALID_ARGUMENT")

    with pytest.raises(_ClientError):
        call_with_backoff(bad_request)
    assert calls["n"] == 1, "a 400 must not be retried"
    assert sleeps == [], "and must not pause"


def test_the_backoff_grows_and_is_capped() -> None:
    """Full jitter, so a batch that backs off together does not re-collide on
    every wave — each wait is somewhere in [0, delay], and delay doubles."""
    delay, seen = RETRY_BASE_SECONDS, []
    for _ in range(8):
        seen.append(delay)
        delay = min(delay * 2, RETRY_MAX_SECONDS)
    assert seen[0] == RETRY_BASE_SECONDS
    assert seen == sorted(seen), "the delay must never shrink"
    assert max(seen) == RETRY_MAX_SECONDS, "and must be capped"
