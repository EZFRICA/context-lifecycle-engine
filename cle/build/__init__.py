"""Three-stage build: resolve -> replay-validate -> assemble.

CLE need: agents born from usage have no a-priori eval suite; their own
history is the suite (BLUEPRINT §3, APU lineage). Invariant 3: a failed
stage burns zero trial occurrences and writes nothing except the build
log. build_image is the pipeline: it owns the single success log line;
each stage logs its own failure."""

import time
from typing import Sequence

from cle.build.assembler import ModelFingerprinter, assemble, parse_trigger
from cle.build.replay import replay_validate
from cle.build.resolver import resolve
from cle.detect.clusters import Embedder
from cle.detect.episodes import DetectorConfig, Message
from cle.oplog import OpLog
from cle.store.backends import StoreBackend
from cle.store.commits import Image, SourceSpec, TriggerSpec


def build_image(
    *,
    source: SourceSpec,
    backend: StoreBackend,
    messages: Sequence[Message],
    window_label: str,
    existing_triggers: Sequence[TriggerSpec],
    embedder: Embedder,
    fingerprinter: ModelFingerprinter,
    config: DetectorConfig,
    oplog: OpLog,
    actor: str,
) -> Image:
    """Run the three stages; only a fully successful build writes.

    On success: the source and the image are stored (both content-
    addressed) and exactly one op:"build" line carries the pre_evidence.
    On failure: the failing stage has already logged its line; nothing
    was written (invariant 3)."""
    started = time.monotonic()

    resolved_refs = resolve(source, backend, oplog, actor)
    trigger = parse_trigger(source)
    replay_outcome = replay_validate(
        trigger=trigger,
        messages=messages,
        window_label=window_label,
        existing_triggers=existing_triggers,
        embedder=embedder,
        config=config,
        oplog=oplog,
        actor=actor,
    )
    image = assemble(
        source=source,
        resolved_refs=resolved_refs,
        trigger=trigger,
        replay_outcome=replay_outcome,
        backend=backend,
        fingerprinter=fingerprinter,
        oplog=oplog,
    )

    # All three stages succeeded — only now does anything touch the store.
    backend.put(source.hash, source.canonical_bytes())
    backend.put(image.hash, image.canonical_bytes())
    oplog.emit(
        "build",
        actor=actor,
        image=image.hash,
        outcome="succeeded",
        pre_evidence=image.pre_evidence.model_dump(),
        source=source.hash[:8],
        latency_ms=round((time.monotonic() - started) * 1000, 3),
    )
    return image
