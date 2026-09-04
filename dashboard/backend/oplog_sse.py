"""Live oplog stream — tail `.cle/log.jsonl` and fan it out over SSE.

One background task tails the log and publishes every new line to an
in-process bus; SSE clients replay the last N lines on connect, then follow
the bus. The demo runner publishes its own `demo_step` events onto the same
bus, so the PULSE feed is a single unified stream. Unknown op types pass
through untouched — the CLE will grow and the dashboard must not crash on
new events.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

REPLAY_ON_CONNECT = 50
_POLL_SECONDS = 0.4


class EventBus:
    """Minimal asyncio pub/sub. Each subscriber gets its own bounded queue;
    a slow client drops oldest events rather than stalling the tailer."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)


def _sse_frame(event_name: str, payload: dict[str, Any]) -> str:
    # One SSE frame: event name = op so the client can route by type.
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def read_tail(log_path: Path, count: int) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    lines = log_path.read_text().splitlines()[-count:]
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"op": "unparsed", "raw": line})
    return out


#: How many bytes of the file's head identify it across polls. One oplog line
#: is comfortably longer than this, so two different logs differ inside it.
_PREFIX_BYTES = 64


def _prefix(log_path: Path) -> bytes:
    """The first bytes of the file, or b"" if it is not there to read."""
    try:
        with log_path.open("rb") as handle:
            return handle.read(_PREFIX_BYTES)
    except OSError:
        return b""


async def tail_log_forever(log_path: Path, bus: EventBus) -> None:
    """Publish new oplog lines to the bus as they are appended.

    Starts at end-of-file so existing history is served only via the
    connect-time replay, not double-counted on the live stream.
    """
    offset = log_path.stat().st_size if log_path.exists() else 0
    prefix = _prefix(log_path)
    while True:
        try:
            if not log_path.exists():
                # Seen mid-wipe. The next file at this path is a different file,
                # so nothing learned from the old one survives.
                offset, prefix = 0, b""
            else:
                size = log_path.stat().st_size
                # Three events look alike from here, and reading from a stale
                # offset splices the middle out of a line — which parses to
                # nothing, so the opening events of a fresh run vanish with no
                # error anywhere and the board starts partway through.
                #
                #   truncated   (`cle clean`)      same file, smaller
                #   replaced    (`full_loop.sh`)   new file at the same path
                #   rewritten                      same file, new content
                #
                # Only the first is caught by comparing sizes. The second is not
                # caught by comparing inodes either, which is what this used to
                # do: a filesystem is free to hand the replacement the inode it
                # just freed, and Linux commonly does — the check passed on APFS
                # and failed in CI for exactly that reason.
                #
                # What actually identifies an append-only file across polls is
                # its head: it never changes while the file is only appended to,
                # and it always changes when the file is replaced by a different
                # one. So that is what is compared.
                head = _prefix(log_path)
                replaced = not (head.startswith(prefix) or prefix.startswith(head))
                if replaced or size < offset:
                    offset = 0
                prefix = head
                if size > offset:
                    with log_path.open("r", encoding="utf-8") as handle:
                        handle.seek(offset)
                        chunk = handle.read()
                        offset = handle.tell()
                    for line in chunk.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            event = {"op": "unparsed", "raw": line}
                        bus.publish(event)
        except Exception:
            # A read race against a concurrent CLI write is transient;
            # never let the tailer die.
            pass
        await asyncio.sleep(_POLL_SECONDS)


async def event_stream(log_path: Path, bus: EventBus) -> AsyncIterator[str]:
    """SSE generator: replay recent history, then follow the live bus."""
    for event in read_tail(log_path, REPLAY_ON_CONNECT):
        yield _sse_frame(event.get("op", "unknown"), event)
    # A one-shot marker so the client knows replay is done and the live
    # feed begins (used to avoid double-flashing zones during replay).
    yield _sse_frame("replay_complete", {"op": "replay_complete"})

    queue = bus.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield _sse_frame(event.get("op", "unknown"), event)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"  # comment frame keeps the socket open
    finally:
        bus.unsubscribe(queue)
