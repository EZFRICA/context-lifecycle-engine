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


async def tail_log_forever(log_path: Path, bus: EventBus) -> None:
    """Publish new oplog lines to the bus as they are appended.

    Starts at end-of-file so existing history is served only via the
    connect-time replay, not double-counted on the live stream.
    """
    stat = log_path.stat() if log_path.exists() else None
    offset = stat.st_size if stat else 0
    inode = stat.st_ino if stat else None
    while True:
        try:
            if log_path.exists():
                stat = log_path.stat()
                size = stat.st_size
                # Two different events look alike from here and only one used to
                # be handled. `cle clean` TRUNCATES: same file, smaller. But
                # `full_loop.sh` starts with `rm -rf`, so the next log.jsonl is a
                # NEW FILE at the same path — and if it happens to reach a size
                # at or above the old offset before the next poll, `size < offset`
                # is false and the tailer reads from a byte offset that belongs to
                # a file that no longer exists. What it splices out of the middle
                # of a line is usually unparseable or empty, so the first events
                # of a fresh run vanish with no error anywhere: the board simply
                # starts partway through.
                #
                # The inode is what actually distinguishes the two, so that is
                # what is compared.
                if stat.st_ino != inode or size < offset:
                    offset = 0
                    inode = stat.st_ino
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
