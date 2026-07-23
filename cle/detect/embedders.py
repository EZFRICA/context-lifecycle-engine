"""Embedder implementations behind the `Embedder` Protocol.

CLE need (BLUEPRINT §9 decision 2, extended): clustering embeds episode
openers into a vector space; the centroids that become agent triggers are
only meaningful WITHIN the space that produced them. So an embedder is a
substrate exactly like the agents' model is — and swapping it invalidates
centroids exactly as a model swap invalidates a `model_fingerprint`, one
layer deeper (this one touches agent identity). Every vector therefore
carries the provenance of the space that made it (`embedder_id`), and the
suite runs OFFLINE against frozen vectors — never the network.

Three implementations:
  * RealEmbedder   — the live substrate (google-genai). Used ONLY by the
    offline cache generator; importing it from a test is a banned dependency
    on the network + a key (asserted in tests/unit/test_embedder_provenance).
  * CachedEmbedder — a pure dict lookup over committed vectors. THE SUITE
    DEFAULT. A cache miss is an ERROR (CacheMissError), never a silent
    recompute — a missing vector means the fixtures and the cache diverged.
  * StubEmbedder   — the deterministic bag-of-hashed-tokens embedder (the
    v1 substrate), for unit tests that use synthetic text not in any cache.

Vectors are L2-normalized (or zero), so `cosine` is the dot product.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

from cle.detect.clusters import HashedTokenEmbedder, Vector

# The frozen substrate for the realistic fixtures (user-selected in the
# embedder-upgrade run). Provenance is provider:model:dim — there is NO
# separate model_version: the google-genai embed response exposes no version
# signal distinct from the id, and a placeholder would give false assurance.
GEMINI_EMBED_MODEL = "gemini-embedding-2"
GEMINI_EMBED_DIM = 768
GEMINI_EMBEDDER_ID = f"google:{GEMINI_EMBED_MODEL}:{GEMINI_EMBED_DIM}"

VECTOR_CACHE = Path(__file__).resolve().parent.parent.parent / "examples" / (
    "vectors.google-gemini-embedding-2-768.json"
)


class CacheMissError(KeyError):
    """A text was requested that is not in the committed vector cache — the
    fixtures and the cache have diverged. Never recompute silently."""


class SpaceMismatchError(Exception):
    """Two vectors from different embedder provenance were compared. A
    centroid is only meaningful in the space that produced it."""


def cache_key(embedder_id: str, text: str) -> str:
    # Keyed by (embedder_id, text): the SAME text under a different embedder
    # is a different point in a different space, so it gets a different key —
    # a model change makes every key miss rather than silently reuse stale
    # vectors.
    return hashlib.sha256(f"{embedder_id}\x00{text}".encode("utf-8")).hexdigest()


def _l2(values: list[float]) -> Vector:
    norm = math.sqrt(sum(v * v for v in values))
    return tuple(values) if norm == 0.0 else tuple(v / norm for v in values)


class StubEmbedder(HashedTokenEmbedder):
    """The deterministic v1 bag-of-tokens embedder, named for its role
    (inherits embedder_id='stub:hashed64')."""


class CachedEmbedder:
    """Pure dict lookup over frozen vectors — the offline suite default."""

    def __init__(self, vectors: dict[str, Vector], embedder_id: str) -> None:
        self._vectors = vectors
        self.embedder_id = embedder_id

    @classmethod
    def from_file(cls, path: Path = VECTOR_CACHE) -> "CachedEmbedder":
        blob = json.loads(path.read_text())
        vectors = {k: tuple(v) for k, v in blob["vectors"].items()}
        return cls(vectors, blob["embedder_id"])

    def embed(self, text: str) -> Vector:
        key = cache_key(self.embedder_id, text)
        try:
            return self._vectors[key]
        except KeyError:
            raise CacheMissError(
                f"no committed vector for text under {self.embedder_id!r}: {text!r}. "
                "Regenerate examples/vectors.*.json (make_vectors.py) or use StubEmbedder."
            ) from None


class RealEmbedder:
    """Live google-genai substrate — OFFLINE-ONLY (cache generation).

    ~20 lines over the official SDK, no framework: the governance rule
    rejects pulling langchain for a single embed call.
    """

    embedder_id = GEMINI_EMBEDDER_ID

    def __init__(self, model: str = GEMINI_EMBED_MODEL, dim: int = GEMINI_EMBED_DIM) -> None:
        import os

        from google import genai  # imported lazily so CI never needs the SDK

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("RealEmbedder needs GEMINI_API_KEY (or GOOGLE_API_KEY) in the env")
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._dim = dim
        self.embedder_id = f"google:{model}:{dim}"

    def embed(self, text: str) -> Vector:
        from google.genai import types

        # One content per call: gemini-embedding-2 treats a list of contents as
        # ONE multi-part document (returns a single embedding), not a batch — so
        # batching by content-list silently collapses N texts to 1 vector.
        result = self._client.models.embed_content(
            model=self._model, contents=text,
            config=types.EmbedContentConfig(output_dimensionality=self._dim),
        )
        return _l2(list(result.embeddings[0].values))

    def embed_many(self, texts: Iterable[str]) -> list[Vector]:
        return [self.embed(t) for t in texts]


def default_embedder() -> CachedEmbedder:
    """The suite default: frozen vectors, offline, miss-is-error."""
    return CachedEmbedder.from_file()
