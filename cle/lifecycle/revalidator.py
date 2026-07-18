"""Re-validator — proof expires (invariant 6).

Contract (BLUEPRINT §5): replay the image's frozen probe set against the
currently served model. Fingerprint drift -> auto-demote to trial and log
{"op":"revalidation_failed", "persistence": {...}}. Outputs are
`Persistence` — the third evidence type; it can demote, never promote.

Drift is LOCALIZED: the image froze per-probe output hashes at build, so
probe_deltas names exactly which probes moved under the new substrate.
"""

import time

from cle.build.assembler import ModelFingerprinter, fingerprint_from_outputs
from cle.oplog import OpLog
from cle.runtime.container import load_image
from cle.store.backends import StoreBackend
from cle.store.commits import Persistence
from cle.store.objects import content_hash


def revalidate(
    *,
    backend: StoreBackend,
    image_hash: str,
    fingerprinter: ModelFingerprinter,
    oplog: OpLog,
    actor: str,
) -> Persistence:
    """Probe the current substrate against the image's frozen set.

    Logs op:"revalidate" when proof holds, op:"revalidation_failed" when
    it drifted. The DEMOTION itself is the caller's move (cle revalidate
    routes it through move_state_tag + topology like any tag op) — one
    op, one line, no hidden writes here."""
    started = time.monotonic()
    image = load_image(backend, image_hash, oplog)
    current_output_hashes = tuple(
        content_hash(output) for output in fingerprinter.outputs(image.probe_set)
    )
    fingerprint_now = fingerprint_from_outputs(current_output_hashes)
    probe_deltas = tuple(
        f"probe-{index}"
        for index, (frozen, current) in enumerate(
            zip(image.probe_output_hashes, current_output_hashes)
        )
        if frozen != current
    )
    persistence = Persistence(
        fingerprint_at_build=image.model_fingerprint,
        fingerprint_now=fingerprint_now,
        probe_deltas=probe_deltas,
    )
    oplog.emit(
        "revalidation_failed" if probe_deltas else "revalidate",
        actor=actor,
        image=image_hash,
        persistence=persistence.model_dump(),
        latency_ms=round((time.monotonic() - started) * 1000, 3),
    )
    return persistence
