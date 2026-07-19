"""Live model fingerprinter — the real substrate footprint (invariant 6).

Replays the image's frozen probe set through the configured LLM and hashes
each output. Probes run at temperature 0 (see get_fingerprint_llm): the
same model yields the same footprint, so a fingerprint delta at
revalidation time means the served MODEL drifted — not that the sampler
rolled differently. That is the whole point of "proof expires."

Determinism caveat (honest): even at temperature 0, a hosted API can carry
residual nondeterminism (backend/version). Rare, and itself a truthful
signal that the substrate is not fixed.
"""

import logging
from typing import Any, Sequence

from cle.llm_provider import get_fingerprint_llm
from cle.store.objects import content_hash

logger = logging.getLogger(__name__)


def response_text(content: Any) -> str:
    """Extract ONLY the generated text from a chat response.

    Newer Gemini models return structured content — a list of parts like
    [{"type":"text","text":"…","extras":{…}}] where `extras` carries
    volatile per-call metadata (ids, token counts). Hashing the whole
    structure would make the fingerprint change on every call even at
    temperature 0, spuriously expiring proof. We keep only the text so a
    fingerprint delta means the MODEL drifted, not the metadata.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content)


class LiveModelFingerprinter:
    """Generates per-probe output hashes from the real configured LLM.

    `model_override` lets the re-validator probe a different real model to
    enact a genuine drift on demand (e.g. gemini-2.0-flash -> gemini-1.5-
    flash) rather than faking one.
    """

    def __init__(self, model_override: str | None = None) -> None:
        self.model = get_fingerprint_llm(model_override)

    def outputs(self, probes: Sequence[str]) -> tuple[str, ...]:
        output_hashes: list[str] = []
        for probe in probes:
            prompt = (
                "You are a system verification probe. Output a short, concise "
                "response to the following query. Do not add conversational "
                f"filler:\n\n{probe}"
            )
            try:
                response = self.model.invoke(prompt)
                output_hashes.append(content_hash(response_text(response.content)))
            except Exception as error:
                logger.error("probe call failed for %r: %s", probe, error)
                # Stable fallback so a transient failure doesn't crash the
                # build; NB this hashes the probe, not the model, so a
                # failed call reads as "no signal", never as false drift.
                output_hashes.append(content_hash(f"probe-call-failed:{probe}"))
        return tuple(output_hashes)
