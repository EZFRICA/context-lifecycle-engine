"""Tamper test (BLUEPRINT §8): corrupt a stored component -> resolve fails,
integrity log fires. The protocol never crashes the process uncontrolled
and never silently injects a corrupt component.
"""

import io
import json

import pytest

from cle.store.objects import Block, IntegrityError, content_hash, fetch_verified
from cle.oplog import OpLog


class FlakyBackend:
    """Returns a corrupt payload for the first `corrupt_reads` fetches."""

    def __init__(self, good: bytes, corrupt_reads: int) -> None:
        self._good = good
        self._corrupt_reads = corrupt_reads

    def get(self, requested_hash: str) -> bytes:
        if self._corrupt_reads > 0:
            self._corrupt_reads -= 1
            return self._good + b"tampered"
        return self._good


def _block_bytes() -> tuple[str, bytes]:
    block = Block(kind="prompt_fragment", payload="weekly recap format")
    return block.hash, block.canonical_bytes()


def _logged_ops(sink: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in sink.getvalue().splitlines()]


def test_clean_fetch_returns_bytes_and_logs_nothing() -> None:
    block_hash, data = _block_bytes()
    sink = io.StringIO()
    result = fetch_verified(FlakyBackend(data, corrupt_reads=0), block_hash, OpLog(sink))
    assert result == data
    assert sink.getvalue() == ""


def test_corrupt_fetch_logs_violation_then_heals_on_refetch() -> None:
    block_hash, data = _block_bytes()
    sink = io.StringIO()
    result = fetch_verified(FlakyBackend(data, corrupt_reads=1), block_hash, OpLog(sink))
    # The caller still gets the good bytes — abort use of the corrupt copy,
    # refetch, carry on. Exactly one violation line fired.
    assert result == data
    ops = _logged_ops(sink)
    assert [op["op"] for op in ops] == ["integrity_violation"]
    assert ops[0]["component"] == block_hash[:8]
    assert ops[0]["actor"] == "system:store"


def test_persistent_corruption_raises_never_injects() -> None:
    block_hash, data = _block_bytes()
    sink = io.StringIO()
    with pytest.raises(IntegrityError):
        fetch_verified(FlakyBackend(data, corrupt_reads=2), block_hash, OpLog(sink))
    # Two violations logged: the original fetch and the failed refetch.
    assert [op["op"] for op in _logged_ops(sink)] == [
        "integrity_violation",
        "integrity_violation",
    ]


def test_every_log_line_is_single_line_json_with_ts() -> None:
    block_hash, data = _block_bytes()
    sink = io.StringIO()
    with pytest.raises(IntegrityError):
        fetch_verified(FlakyBackend(data, corrupt_reads=2), block_hash, OpLog(sink))
    for line in sink.getvalue().splitlines():
        record = json.loads(line)  # each line parses standalone
        assert "ts" in record and "op" in record and "actor" in record
