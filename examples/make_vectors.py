"""Offline vector-cache generator — the ONLY RealEmbedder caller.

Embeds every distinct text in the realistic committed fixtures (GDG +
holdout) plus an explicit `EXTRA_TEXTS` list (the R7 injected-contradiction
strings, which need REAL vectors for the world_state retest), and freezes the
result to a committed JSON keyed by cache_key(embedder_id, text). CI then reads
those vectors through CachedEmbedder — no key, no network.

Adjustment 3 (cache coverage): fixture texts + EXTRA_TEXTS are covered here;
every other synthetic/demo text uses StubEmbedder explicitly and never reaches
this cache.

Run (needs GEMINI_API_KEY, network — NOT run in CI):
    .venv/bin/python examples/make_vectors.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cle.detect.embedders import RealEmbedder, VECTOR_CACHE, cache_key  # noqa: E402

EX = Path(__file__).resolve().parent
FIXTURES = ["prompt_history_gdg.jsonl", "prompt_history_holdout.jsonl"]

# R7 world_state retest — a MODERATE opposing-directive pair on the events
# (tool-bearing) intent. Same strings the R7 test uses, so they resolve from
# this committed cache. The opener it pairs with is already a fixture text.
EXTRA_TEXTS = [
    "lock the saturday morning slot, thats final",
    "cancel saturday, move it to a weekday evening instead",
    "keep it exactly where it is, dont touch the booking",
    "scrap this venue entirely and start the search over",
]


def collect_texts() -> list[str]:
    """Every string any consumer will embed.

    Two distinct consumers, two shapes of text:
      * clustering / replay embed the episode OPENER — an individual message;
      * the stability classifier embeds `_directive_text(episode)`, which is the
        episode's follow-ups JOINED into one string. That join is not any single
        message, so covering only message texts would miss it (found at R4, not
        at R2 — recorded in the journal).
    """
    from cle.detect.episodes import DetectorConfig, Message, segment
    from cle.detect.stability import _directive_text

    config = DetectorConfig()
    texts: set[str] = set()
    for name in FIXTURES:
        raw = [json.loads(line) for line in (EX / name).read_text().splitlines() if line.strip()]
        for record in raw:
            texts.add(record["text"])
        for episode in segment([Message.model_validate(r) for r in raw], config):
            texts.add(_directive_text(episode))
    texts.update(EXTRA_TEXTS)
    return sorted(t for t in texts if t)


def main() -> None:
    texts = collect_texts()
    embedder = RealEmbedder()
    started = time.monotonic()
    vectors = embedder.embed_many(texts)
    elapsed = time.monotonic() - started
    cache = {cache_key(embedder.embedder_id, t): list(v) for t, v in zip(texts, vectors)}
    dim = len(vectors[0]) if vectors else 0
    VECTOR_CACHE.write_text(json.dumps(
        {"embedder_id": embedder.embedder_id, "dim": dim, "count": len(cache), "vectors": cache}))
    print(f"embedded {len(texts)} distinct texts (dim={dim}) in {elapsed:.1f}s")
    print(f"api_calls={len(texts)} (one content per call)")
    print(f"cache_vectors={len(cache)}")
    print(f"wrote {VECTOR_CACHE.name} ({VECTOR_CACHE.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
