"""Embedder implementations behind the `Embedder` Protocol.

CLE need (BLUEPRINT §9 decision 2, extended): clustering embeds episode
openers into a vector space; the centroids that become agent triggers are
only meaningful WITHIN the space that produced them. So an embedder is a
substrate exactly like the agents' model is - and swapping it invalidates
centroids exactly as a model swap invalidates a `model_fingerprint`, one
layer deeper (this one touches agent identity). Every vector therefore
carries the provenance of the space that made it (`embedder_id`), and the
suite runs OFFLINE against frozen vectors - never the network.

Three implementations:
  * RealEmbedder - the live substrate (google-genai). Used ONLY by the
    offline cache generator; importing it from a test is a banned dependency
    on the network + a key (asserted in tests/unit/test_embedder_provenance).
  * CachedEmbedder - a pure dict lookup over committed vectors. THE SUITE
    DEFAULT. A cache miss is an ERROR (CacheMissError), never a silent
    recompute - a missing vector means the fixtures and the cache diverged.
  * StubEmbedder - the deterministic bag-of-hashed-tokens embedder (the
    v1 substrate), for unit tests that use synthetic text not in any cache.

Vectors are L2-normalized (or zero), so `cosine` is the dot product.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from cle.batch_guard import (
    assert_batch_varied,
    assert_embeddable,
    assert_unit_norm,
    text_digest,
)
from cle.detect.clusters import HashedTokenEmbedder, Vector
from cle.logs import get_logger

logger = get_logger(__name__)

# The frozen substrate for the realistic fixtures (user-selected in the
# embedder-upgrade run). Provenance is provider:model:dim - there is NO
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
    """A text was requested that is not in the committed vector cache - the
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
    # is a different point in a different space, so it gets a different key -
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
            f"the model returned no vector for {text_digest(text)}. The call succeeded "
            "and the response carried no embedding, so this is a response-shape "
            "failure, not a network error."
        )
    return list(values)


class StubEmbedder(HashedTokenEmbedder):
    """The deterministic v1 bag-of-tokens embedder, named for its role
    (inherits embedder_id='stub:hashed64')."""


class CachedEmbedder:
    """Pure dict lookup over frozen vectors - the offline suite default."""

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
        # returns 0.57 to 0.60 (measured min 0.572648, max 0.599283 over 20
        # vectors): it runs `gemini-embedding-001` on Vertex, a
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
        # opener surfaces as `CacheMissError` - which names the wrong defect and
        # sends the reader to regenerate a cache that is not the problem.
        assert_embeddable(text, where="CachedEmbedder.embed")
        key = cache_key(self.embedder_id, text)
        try:
            return self._vectors[key]
        except KeyError:
            raise CacheMissError(
                f"no committed vector for text under {self.embedder_id!r}: "
                f"{text_digest(text)}, cache key {key}. "
                "Regenerate examples/vectors.*.json (make_vectors.py) or use StubEmbedder."
            ) from None


#: Retry policy for the live embedding surface. Three attempts spanning at most
#: a few seconds: long enough to ride out a burst, short enough that a genuinely
#: exhausted quota still fails while the operator is watching rather than an
#: hour later.
RETRY_ATTEMPTS = 3
RETRY_BASE_SECONDS = 1.0
RETRY_MAX_SECONDS = 8.0


def _is_rate_limit(error: Exception) -> bool:
    """True for 429 / RESOURCE_EXHAUSTED, whatever the SDK wraps it in.

    Matched on the message rather than an exception class on purpose: the
    google-genai SDK raises `ClientError` for every 4xx, so the class says
    nothing about which one, and pinning a private class here would make the
    retry silently stop working on an SDK upgrade.
    """
    # Underscores are stripped so both spellings match: the SDK writes
    # `RESOURCE_EXHAUSTED` in the message and google.api_core names the class
    # `ResourceExhausted`.
    text = f"{type(error).__name__} {error}".upper().replace("_", "")
    return "429" in text or "RESOURCEEXHAUSTED" in text


def call_with_backoff(call: Callable[[], Any]) -> Any:
    """Retry a rate-limited call; re-raise anything else immediately.

    Without this the sample size of a live measurement is set by the quota
    rather than by the operator. Measured: comparing 186 cached vectors against
    AI Studio lost 32 of them to 429s, and an immediate second pass lost 86 - so
    the figure that came back described whatever survived the quota, and a rerun
    described something else.

    Only 429 / RESOURCE_EXHAUSTED is retried. A 400, a 403 or a malformed
    request fails identically on every attempt, and retrying those turns a clear
    error into a slow one.

    Module-level and free of any client, for the same reason as
    `vector_from_response`: no test may import `RealEmbedder`, so a retry loop
    that lived on the class could only ever be tested against a copy of itself.
    """
    delay = RETRY_BASE_SECONDS
    # Every attempt but the last may retry; the last one's error propagates as
    # it is, with no re-raise needed. Bounded by construction - no path loops
    # forever - and with no trailing raise that no input could reach.
    for attempt in range(1, RETRY_ATTEMPTS):
        try:
            return call()
        except Exception as error:
            if not _is_rate_limit(error):
                raise
            # A run that slows down for minutes with nothing on screen reads as
            # a hang; the retry is what it is doing.
            logger.warning("rate limited (%s); retry %d of %d within %.1fs",
                           type(error).__name__, attempt, RETRY_ATTEMPTS - 1, delay)
            # Full jitter: a batch that backs off in lockstep re-collides on
            # every wave, so each caller waits somewhere in [0, delay].
            time.sleep(random.uniform(0.0, delay))
            delay = min(delay * 2, RETRY_MAX_SECONDS)
    return call()


class RealEmbedder:
    """Live google-genai substrate - OFFLINE-ONLY (cache generation).

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
        # ONE multi-part document (returns a single embedding), not a batch - so
        # batching by content-list silently collapses N texts to 1 vector.
        result = call_with_backoff(
            lambda: self._client.models.embed_content(
                model=self._model, contents=text,
                config=types.EmbedContentConfig(output_dimensionality=self._dim),
            )
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


#: EmbeddingGemma-300m, run locally through onnxruntime. Three coordinates make
#: the space, not one: the model, the QUANTISATION (fp32, fp16, int8, q4 are
#: different weights and so different geometries) and the TASK PREFIX the model
#: was trained with. Measured on this repository's fixtures, the prefix moved F
#: from 0.58 to 0.90 - as much as choosing another model - so it is in the id.
ONNX_MODEL = "embeddinggemma-300m"
ONNX_DIM = 768
ONNX_VARIANT = "fp16"
ONNX_TEMPLATE = "query"
ONNX_TEMPLATES = {
    "query": "task: search result | query: {text}",
    "clustering": "task: clustering | query: {text}",
    "document": "title: none | text: {text}",
}
#: Tokens per text and texts per forward pass. An episode opener is a sentence;
#: the cap keeps a batch's padding from dominating a CPU run.
ONNX_MAX_TOKENS = 256
ONNX_BATCH = 16


def onnx_embedder_id(variant: str = ONNX_VARIANT, template: str = ONNX_TEMPLATE) -> str:
    return f"onnx:{ONNX_MODEL}-{variant}:{template}:{ONNX_DIM}"


class OnnxEmbedder:
    """A real embedding model that runs locally, on CPU, for nothing.

    The third kind of "real": `RealEmbedder` bills per call and needs a key,
    `CachedEmbedder` is free but answers only for texts somebody already paid
    for, and this one embeds ANY text, offline, at ~25 ms per opener. For a
    deployment whose constraint is that user text must not leave the machine,
    that difference is the whole argument.

    NOT a drop-in for `gemini-embedding-2`. It is another vector space: its
    cosines sit higher (cross-intent median 0.71-0.73 against 0.61), its
    calibrated threshold is 0.46 rather than 0.775, and at their respective best
    thresholds the two spaces agree at ARI +0.646 - close scores, different
    partitions. A topology born here is comparable only with itself, which is
    what `embedder_id` and `EmbeddingConfigMismatchError` enforce.

    The weights are NOT in this repository: `$CLE_ONNX_MODEL_DIR` must point at
    a directory holding the exported graph for the variant, its weight sidecar
    and the model's tokenizer file. `examples/onnx_embedding_bench.py` names the
    download command and the exact file names.
    """

    def __init__(self, model_dir: Path | str | None = None, variant: str = ONNX_VARIANT,
                 template: str = ONNX_TEMPLATE) -> None:
        # Tested BEFORE building a Path: `Path("")` is `.`, which is truthy and
        # turns a missing variable into a confusing "file not found" about the
        # working directory.
        named = str(model_dir) if model_dir else os.environ.get("CLE_ONNX_MODEL_DIR", "")
        if not named.strip():
            raise RuntimeError(
                "OnnxEmbedder needs $CLE_ONNX_MODEL_DIR pointing at a directory holding "
                f"onnx/model_{variant}.onnx and tokenizer.json. No default: a path that "
                "looks configured and is not is how a run embeds in a space nobody chose. "
                "See examples/onnx_embedding_bench.py for the download command."
            )
        root = Path(named)
        if template not in ONNX_TEMPLATES:
            raise ValueError(f"unknown ONNX task prefix {template!r}; "
                             f"expected one of {sorted(ONNX_TEMPLATES)}")
        graph = root / "onnx" / f"model_{variant}.onnx"
        if not graph.exists():
            raise FileNotFoundError(f"{graph} is missing; $CLE_ONNX_MODEL_DIR is {root}")
        # Lazily, like the google SDK above: neither onnxruntime nor tokenizers is
        # a declared dependency, and the engine must import without them.
        import onnxruntime
        from tokenizers import Tokenizer

        self._session = onnxruntime.InferenceSession(
            str(graph), providers=["CPUExecutionProvider"])
        self._tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=ONNX_MAX_TOKENS)
        self._tokenizer.enable_padding()
        self._template = ONNX_TEMPLATES[template]
        self._seen: dict[str, Vector] = {}
        self.embedder_id = onnx_embedder_id(variant, template)

    def embed(self, text: str) -> Vector:
        assert_embeddable(text, where="OnnxEmbedder.embed")
        if text not in self._seen:
            self.embed_many([text])
        return self._seen[text]

    def embed_many(self, texts: Iterable[str]) -> list[Vector]:
        """One forward pass per batch; repeated texts are embedded once.

        The guards are HERE as well as in `embed`, not only there: a batch path
        that skips them is exactly how a guard becomes decorative. Callers in
        this repository use this method directly.
        """
        import math

        import numpy as np

        wanted = list(dict.fromkeys(texts))
        for text in wanted:
            # The only OUTBOUND guard on this path. Nothing is billed here, but
            # an empty opener embedded locally still enters clustering as an
            # arbitrary point pretending to name an intent.
            assert_embeddable(text, where="OnnxEmbedder.embed_many")
        missing = [t for t in wanted if t not in self._seen]
        for start in range(0, len(missing), ONNX_BATCH):
            chunk = missing[start:start + ONNX_BATCH]
            encoded = self._tokenizer.encode_batch(
                [self._template.format(text=t) for t in chunk])
            ids = np.array([e.ids for e in encoded], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            # `run` is typed as returning a union that includes a sparse tensor
            # and a dict; the output we ask for is dense. Narrowed here rather
            # than asserted in a comment, so the type is what the code says.
            raw = np.asarray(self._session.run(
                ["sentence_embedding"], {"input_ids": ids, "attention_mask": mask})[0])
            for text, vector in zip(chunk, raw):
                # Normalised HERE, explicitly, at the boundary this class owns.
                # The model returns unit vectors today (measured: min and max
                # 1.000000 over a batch), and asserting that rather than relying
                # on it is the rule `assert_unit_norm` exists for - BigQuery's
                # 0.58-norm vectors produced plausible numbers from an unrelated
                # geometry precisely because nobody checked.
                norm = math.sqrt(sum(float(x) * float(x) for x in vector))
                unit = tuple(float(x) / norm for x in vector) if norm else tuple(
                    float(x) for x in vector)
                assert_unit_norm(unit, where=self.embedder_id)
                self._seen[text] = unit
        vectors = [self._seen[t] for t in wanted]
        # A batch that returns is not a batch that worked: a wrong attention
        # mask, a collapsed input, a model loaded half-initialised all return
        # the right NUMBER of vectors. `RealEmbedder` carries this guard for a
        # collapse that actually happened; a local runtime is not exempt.
        assert_batch_varied([repr(v) for v in vectors],
                            label=f"{self.embedder_id}.embed_many")
        return vectors


def default_embedder() -> CachedEmbedder:
    """The suite default: frozen vectors, offline, miss-is-error."""
    return CachedEmbedder.from_file()


EMBEDDER_KINDS = ("stub", "cached", "real", "onnx")


def open_embedder(kind: str | None = None):
    """Select the embedder this instance runs detection on - ONE selection point.

    `kind` defaults to $CLE_EMBEDDER, itself defaulting to "stub", so existing
    state and existing invocations keep working untouched. The default is NOT
    "cached" even though cached vectors are better: every topology written so
    far records `embedder_id: stub:hashed64`, and silently switching would make
    the next write assert a vector space the history was not produced in.
    Changing it is opt-in, and `EmbeddingConfigMismatchError` is what catches
    doing it to an existing history.

    THREE kinds, because "real" is two different things and conflating them
    would hide which one is being paid for:

      * stub - bag-of-hashed-tokens. Free, deterministic, and a vector space
        in which the contradiction taxonomy only *appears* to work (era A).
      * cached - the REAL `gemini-embedding-2` geometry, read from the frozen
        247-vector cache. Free, offline, reproducible; a text outside the cache
        is a CacheMissError, never a silent recompute. This is real detection
        for the corpus the cache was built from.
      * real - live `gemini-embedding-2`. Works on ANY text and costs money
        per call, over the network.
      * onnx - EmbeddingGemma-300m from a local file. Works on ANY text, costs
        nothing, and never leaves the machine. A DIFFERENT vector space from
        the three above, with its own calibrated threshold; needs
        `$CLE_ONNX_MODEL_DIR` and the onnxruntime/tokenizers packages, which
        this project does not declare.

    `cached` and `real` share one `embedder_id`, so a topology written under one
    is comparable with the other: the vectors are the same geometry, only the
    delivery differs. That is deliberate - it is why the cache is worth having.
    """
    kind = (kind or os.environ.get("CLE_EMBEDDER") or "stub").lower()
    if kind == "stub":
        return StubEmbedder()
    if kind == "cached":
        return CachedEmbedder.from_file()
    if kind == "real":
        return RealEmbedder()
    if kind == "onnx":
        return OnnxEmbedder(
            variant=os.environ.get("CLE_ONNX_VARIANT", ONNX_VARIANT),
            template=os.environ.get("CLE_ONNX_TEMPLATE", ONNX_TEMPLATE),
        )
    raise ValueError(f"unknown embedder kind {kind!r}; expected one of {EMBEDDER_KINDS}")


# ── embedding configuration, as an AGGREGATION KEY ──────────────────────────
# CLE need (level-2 preparation): two instances running the SAME embedder at
# 0.775 and at 0.72 do not birth the same agents from the same usage. A
# population report that aggregates topologies from different configurations
# measures its own instrumentation, not its population - the v1 failure mode
# transposed, and this time with no test suite to catch it.
#
# So the configuration is a KEY, not metadata: a topology history without it is
# comparable to nothing. It is recorded at TOPOLOGY scope (never per agent) and
# written only by the lifecycle engine (invariant 1).

from pydantic import BaseModel  # noqa: E402

# Where each threshold came from. A configuration whose calibration nobody can
# name is not a configuration, it is a guess - so this is required, and the
# honest answer for the stub is that it was never swept.
CALIBRATION_PROVENANCE: dict[str, str] = {
    "stub:hashed64":
        "v1 default, never swept; bag-of-tokens only appears to separate intents "
        "because identical openers repeat (docs/METRICS.md, era A)",
    GEMINI_EMBEDDER_ID:
        "swept 0.60-0.95 on the realistic fixtures; adopted on ONE independent "
        "confirmation - the process-independent holdout, never consulted to pick "
        "it (docs/METRICS.md, era C). The in-sample GDG peak is NOT evidence.",
    onnx_embedder_id():
        "swept 0.30-0.95 at 0.01 on both offline fixtures (docs/FINDINGS.md "
        "§8). The process-independent holdout peaks at F 0.904 on a 0.37-0.42 "
        "plateau and GDG peaks at F 0.897 at 0.50 - the inversion the corpora "
        "keep producing - so 0.46 is the value that maximises the WORSE of the "
        "two (0.849) and keeps purity at 96% on the holdout. Only the fp16 "
        "variant under the `query` prefix was measured; another quantisation "
        "or prefix is another space and has no entry here.",
}


class EmbeddingConfig(BaseModel, frozen=True):
    """The vector space a topology was produced in - its aggregation key."""

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
    """Derive the config from the embedder actually in use - never hand-written."""
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
