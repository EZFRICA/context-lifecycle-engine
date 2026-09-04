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
import os
import json
import math
from pathlib import Path
from typing import Iterable

from cle.batch_guard import assert_batch_varied, assert_embeddable, assert_unit_norm
from cle.detect.clusters import HashedTokenEmbedder, Vector

# The frozen substrate for the realistic fixtures (user-selected in the
# embedder-upgrade run). Provenance is provider:model:dim — there is NO
# separate model_version: the google-genai embed response exposes no version
# signal distinct from the id, and a placeholder would give false assurance.
GEMINI_EMBED_MODEL = "gemini-embedding-2"
GEMINI_EMBED_DIM = 768
GEMINI_EMBEDDER_ID = f"google:{GEMINI_EMBED_MODEL}:{GEMINI_EMBED_DIM}"

# The committed cache. `$CLE_VECTOR_CACHE` points at a different one, which is
# how a corpus larger than the committed fixtures runs through the CLI without
# paying for `--embedder real` on every build: pre-embed once into a side cache,
# then read it as often as needed.
#
# The override is a PATH, never a space. `CachedEmbedder` reads its
# `embedder_id` from the file, `assert_unit_norm` checks the vectors on load,
# and `EmbeddingConfigMismatchError` refuses a topology whose space does not
# match, so pointing this at a foreign cache fails loudly rather than silently
# changing the geometry a history was born in.
VECTOR_CACHE = Path(
    os.environ.get("CLE_VECTOR_CACHE")
    or Path(__file__).resolve().parent.parent.parent / "examples"
    / "vectors.google-gemini-embedding-2-768.json"
)


class CacheMissError(KeyError):
    """A text was requested that is not in the committed vector cache — the
    fixtures and the cache have diverged. Never recompute silently."""


class EmptyEmbeddingError(RuntimeError):
    """The embedding call succeeded and returned no vector.

    Distinct from a network failure, which raises on its own: here the request
    completed, the response parsed, and it simply holds no embedding. Without
    this the failure surfaces as `NoneType` has no attribute, several frames
    from the call that caused it.
    """


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


def vector_from_response(result, text: str) -> list[float]:
    """Pull the vector out of an embed response, or say why there is none.

    Module-level and free of any client so the suite can test it without
    importing `RealEmbedder`, which no test may do: the live embedder is a
    dependency on the network and a key, and that ban is itself asserted
    (`test_no_test_module_imports_real_embedder`).
    """
    embeddings = getattr(result, "embeddings", None) or []
    values = embeddings[0].values if embeddings else None
    if not values:
        raise EmptyEmbeddingError(
            f"the model returned no vector for {text[:60]!r}. The call succeeded "
            "and the response carried no embedding, so this is a response-shape "
            "failure, not a network error."
        )
    return list(values)


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
        # Norm check at the boundary, once, on load. A cache file is the one
        # place a vector enters the CLE without passing through an embedder that
        # normalises, so a cache built elsewhere would quietly stop `cosine`
        # being a cosine. BigQuery's `ML.GENERATE_EMBEDDING`, for instance,
        # returns 0.58 to 0.60: it runs `gemini-embedding-001` on Vertex, a
        # different model from `gemini-embedding-2` (cosine between the two
        # spaces on the same texts: 0.040084).
        #
        # Sampled rather than exhaustive: the failure mode is a whole file
        # produced by the wrong source, never one bad row.
        for key in list(vectors)[:32]:
            assert_unit_norm(vectors[key], where=f"vector cache {path.name}")
        return cls(vectors, blob["embedder_id"])

    def embed(self, text: str) -> Vector:
        # Same guard offline. Nothing is billed here, but without it an empty
        # opener surfaces as `CacheMissError` — which names the wrong defect and
        # sends the reader to regenerate a cache that is not the problem.
        assert_embeddable(text, where="CachedEmbedder.embed")
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

    TWO SURFACES serve this model, and which one is in use decides whether a
    real corpus can be embedded at all:

      * AI Studio, by API key. What `$GEMINI_API_KEY` selects. Its rate limit
        is low enough that a build over ~100 episodes dies mid-way on a
        `429 RESOURCE_EXHAUSTED`, having already paid for every call it made.
      * Vertex, by application-default credentials (`gcloud auth
        application-default login`), at location `global`. Selected by setting
        `$CLE_VERTEX_PROJECT`. Project-level quota, so a real corpus completes.

    They are the SAME vector space, not two models: re-embedding cached texts
    through Vertex reproduces the AI Studio vectors at cosine 1.000000
    (measured, n=3). `embedder_id` is therefore identical on both, which is what
    lets a topology born on one be read by the other.

    Note the location: `gemini-embedding-2` is served at `global` and 404s at
    `us-central1` and `europe-west1`.
    """

    embedder_id = GEMINI_EMBEDDER_ID

    def __init__(self, model: str = GEMINI_EMBED_MODEL, dim: int = GEMINI_EMBED_DIM) -> None:
        import os

        from dotenv import load_dotenv
        from google import genai  # imported lazily so CI never needs the SDK

        # Load `.env` here rather than relying on an earlier import having done
        # it. Reading `os.environ` raw would make the key's presence depend on
        # whether something else imported `cle.llm_provider` first, and callers
        # would each need their own `load_dotenv()` to be safe. Loading is
        # idempotent and never overrides an already-set variable, so an explicit
        # export still wins.
        load_dotenv()
        # Vertex first when a project is named: it is the surface with a quota
        # large enough to finish a corpus. Falling back to the key keeps every
        # existing invocation working untouched.
        vertex_project = os.environ.get("CLE_VERTEX_PROJECT")
        if vertex_project:
            self._client = genai.Client(
                vertexai=True, project=vertex_project,
                location=os.environ.get("CLE_VERTEX_LOCATION", "global"),
            )
        else:
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "RealEmbedder needs CLE_VERTEX_PROJECT (Vertex, via `gcloud auth "
                    "application-default login`) or GEMINI_API_KEY (AI Studio) in the env"
                )
            self._client = genai.Client(api_key=api_key)
        self._model = model
        self._dim = dim
        self.embedder_id = f"google:{model}:{dim}"

    def embed(self, text: str) -> Vector:
        from google.genai import types

        # Outbound, before the billed call.
        assert_embeddable(text, where="RealEmbedder.embed")
        # One content per call: gemini-embedding-2 treats a list of contents as
        # ONE multi-part document (returns a single embedding), not a batch — so
        # batching by content-list silently collapses N texts to 1 vector.
        result = self._client.models.embed_content(
            model=self._model, contents=text,
            config=types.EmbedContentConfig(output_dimensionality=self._dim),
        )
        # A response can come back shaped correctly and carry no vector, and
        # reaching for `[0].values` then dies on `NoneType` a frame from the
        # call with nothing naming the cause. Same family as the other guards
        # here: the call returned, and returning is not the same as working.
        return _l2(vector_from_response(result, text))

    def embed_many(self, texts: Iterable[str]) -> list[Vector]:
        vectors = [self.embed(t) for t in texts]
        # The batching collapse this guard names is not hypothetical: an early
        # run passed 190 texts as one content list and got ONE vector back,
        # caught only by eyeballing a 34 KB file.
        assert_batch_varied([repr(v) for v in vectors], label="RealEmbedder.embed_many")
        return vectors


def default_embedder() -> CachedEmbedder:
    """The suite default: frozen vectors, offline, miss-is-error."""
    return CachedEmbedder.from_file()


EMBEDDER_KINDS = ("stub", "cached", "real")


def open_embedder(kind: str | None = None):
    """Select the embedder this instance runs detection on — ONE selection point.

    `kind` defaults to $CLE_EMBEDDER, itself defaulting to "stub", so existing
    state and existing invocations keep working untouched. The default is NOT
    "cached" even though cached vectors are better: every topology written so
    far records `embedder_id: stub:hashed64`, and silently switching would make
    the next write assert a vector space the history was not produced in.
    Changing it is opt-in, and `EmbeddingConfigMismatchError` is what catches
    doing it to an existing history.

    THREE kinds, because "real" is two different things and conflating them
    would hide which one is being paid for:

      * stub   — bag-of-hashed-tokens. Free, deterministic, and a vector space
        in which the contradiction taxonomy only *appears* to work (era A).
      * cached — the REAL `gemini-embedding-2` geometry, read from the frozen
        247-vector cache. Free, offline, reproducible; a text outside the cache
        is a CacheMissError, never a silent recompute. This is real detection
        for the corpus the cache was built from.
      * real   — live `gemini-embedding-2`. Works on ANY text and costs money
        per call. The only kind that can embed text nobody has embedded before.

    `cached` and `real` share one `embedder_id`, so a topology written under one
    is comparable with the other: the vectors are the same geometry, only the
    delivery differs. That is deliberate — it is why the cache is worth having.
    """
    kind = (kind or os.environ.get("CLE_EMBEDDER") or "stub").lower()
    if kind == "stub":
        return StubEmbedder()
    if kind == "cached":
        return CachedEmbedder.from_file()
    if kind == "real":
        return RealEmbedder()
    raise ValueError(f"unknown embedder kind {kind!r}; expected one of {EMBEDDER_KINDS}")


# ── embedding configuration, as an AGGREGATION KEY ──────────────────────────
# CLE need (level-2 preparation): two instances running the SAME embedder at
# 0.775 and at 0.72 do not birth the same agents from the same usage. A
# population report that aggregates topologies from different configurations
# measures its own instrumentation, not its population — the v1 failure mode
# transposed, and this time with no test suite to catch it.
#
# So the configuration is a KEY, not metadata: a topology history without it is
# comparable to nothing. It is recorded at TOPOLOGY scope (never per agent) and
# written only by the lifecycle engine (invariant 1).

from pydantic import BaseModel  # noqa: E402

# Where each threshold came from. A configuration whose calibration nobody can
# name is not a configuration, it is a guess — so this is required, and the
# honest answer for the stub is that it was never swept.
CALIBRATION_PROVENANCE: dict[str, str] = {
    "stub:hashed64":
        "v1 default, never swept; bag-of-tokens only appears to separate intents "
        "because identical openers repeat (docs/METRICS.md, era A)",
    GEMINI_EMBEDDER_ID:
        "swept 0.60-0.95 on the realistic fixtures; adopted on ONE independent "
        "confirmation — the process-independent holdout, never consulted to pick "
        "it (docs/METRICS.md, era C). The in-sample GDG peak is NOT evidence.",
}


class EmbeddingConfig(BaseModel, frozen=True):
    """The vector space a topology was produced in — its aggregation key."""

    embedder_id: str
    cluster_threshold: float
    calibration: str


class UnknownCalibrationError(KeyError):
    """No calibration provenance is recorded for this embedder.

    Deliberately loud. Defaulting to "unknown" would let a topology into a
    population aggregate while claiming a configuration nobody can account for,
    which is exactly the comparison this key exists to prevent.
    """


def embedding_config_for(embedder: object) -> EmbeddingConfig:
    """Derive the config from the embedder actually in use — never hand-written."""
    from cle.detect.clusters import cluster_threshold_for
    from cle.detect.episodes import DetectorConfig

    embedder_id = getattr(embedder, "embedder_id", None)
    if not embedder_id:
        raise UnknownCalibrationError(
            f"{type(embedder).__name__} exposes no embedder_id; a topology cannot "
            "record the vector space it was produced in"
        )
    if embedder_id not in CALIBRATION_PROVENANCE:
        raise UnknownCalibrationError(
            f"no calibration provenance recorded for {embedder_id!r}; add it to "
            "CALIBRATION_PROVENANCE in the same change that introduces the embedder"
        )
    return EmbeddingConfig(
        embedder_id=embedder_id,
        cluster_threshold=cluster_threshold_for(
            embedder_id, DetectorConfig().cluster_similarity_threshold
        ),
        calibration=CALIBRATION_PROVENANCE[embedder_id],
    )
