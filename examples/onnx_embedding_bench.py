"""EmbeddingGemma-300m through ONNX, measured against the space the engine runs on.

BILLS NOTHING, CALLS NOTHING. The candidate space is a local ONNX file; the
reference space is the committed cache
`examples/vectors.google-gemini-embedding-2-768.json`, whose 247 vectors were
paid for once. The labels are the planted intents of
`examples/gdg_ground_truth.json`. So this bench can be re-run by a reader with
no key, no cloud project and no budget, which is the only reason its figures
belong beside the billed ones.

WHAT COUNTS AS A SPACE HERE, and why the name is this long. A vector space in
this repo is `(model, surface, dimension)` because a centroid is only comparable
inside the space that produced it (BLUEPRINT §4). A locally-run model adds two
coordinates that change the geometry and that nothing else in the codebase has
had to name yet:

  * THE QUANTISATION. `onnx-community/embeddinggemma-300m-ONNX` publishes fp32,
    fp16, int8, q4, q4f16 and a no-gather q4. They are not sizes of one space,
    they are different spaces: the weights differ, so the cosines differ. This
    bench names the one it ran in its space id and refuses to average over
    variants.
  * THE PROMPT TEMPLATE. EmbeddingGemma is trained with task prefixes, and the
    prefix is part of the embedding function: the same sentence under
    `task: clustering` and under `title: none | text:` lands somewhere else.
    Clustering is what level 1 does, so that is the prefix used, and it is in
    the space id too.

WHAT THIS BENCH DOES NOT CLAIM. Not that one space is better. The threshold is
swept because it is a property of the space, never a constant
(`CLUSTER_THRESHOLD_BY_EMBEDDER`), and a space is only readable at its own
calibrated value; comparing two spaces at one number measures the number. The
agreement figure (adjusted Rand index between the two clusterings, each at its
own best threshold) is there for the same reason: it says whether the two spaces
group the same corpus the same way, which is a different question from which one
scores higher.

REQUIREMENTS, named here rather than declared, following the rule the dependency
block in `pyproject.toml` states: `onnxruntime` and `tokenizers` are needed by
this file alone and pull no torch.

    uv run --with onnxruntime --with tokenizers python examples/onnx_embedding_bench.py \\
        --model-dir <dir holding onnx/model_fp16.onnx and tokenizer.json>

Get that directory with (622 MB, ungated):

    huggingface-cli download onnx-community/embeddinggemma-300m-ONNX \\
        onnx/model_fp16.onnx onnx/model_fp16.onnx_data tokenizer.json \\
        --local-dir <dir>
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import pathlib
import sys
import time
from collections import Counter
from typing import Iterable, Sequence

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cle.batch_guard import assert_batch_varied, assert_unit_norm  # noqa: E402
from cle.detect.clusters import CLUSTER_THRESHOLD_BY_EMBEDDER  # noqa: E402
from cle.detect.embedders import CachedEmbedder  # noqa: E402
from cle.detect.episodes import DetectorConfig, Message, segment  # noqa: E402
from cle.logs import configure_logging, get_logger  # noqa: E402
from cle.population.grouping import Precomputed, group  # noqa: E402

log = get_logger("onnx_embedding_bench")

GDG_HISTORY = ROOT / "examples" / "prompt_history_gdg.jsonl"
GROUND_TRUTH = ROOT / "examples" / "gdg_ground_truth.json"
HOLDOUT_HISTORY = ROOT / "examples" / "prompt_history_holdout.jsonl"

#: The corpora this bench knows. Both are offline fixtures with planted labels;
#: neither is real user text.
CORPORA = ("holdout", "gdg")

#: The holdout's three planted patterns, which have no sidecar: `make_holdout.py`
#: imports nothing from `cle` and writes only the history, so the fixture's own
#: thread prefixes are the record of what was planted. Everything else there is
#: `noise`, and noise is not an intent to be recovered.
HOLDOUT_NOISE = "noise"

#: WHY THE GDG LABEL IS THE THREAD PREFIX AND NOT `labeled_threads`. That sidecar
#: field maps a thread to a CONFLICT kind (`world_state`, `intra_cluster`) for the
#: contradiction taxonomy, not to an intent. Reading it as the intent is a mistake
#: this bench made on its first run: three of the seven planted intents vanished
#: and the measurement ran on 44 openers instead of 92, with no error anywhere.
GDG_INTENT_FROM_THREAD = "prefix before the first '-'"

#: EmbeddingGemma's task prefixes. Level 1 clusters episode openers, so the
#: clustering prefix is the one under test; the others are listed because the
#: choice is a coordinate of the space, not a detail.
PROMPT_TEMPLATES = {
    "clustering": "task: clustering | query: {text}",
    "document": "title: none | text: {text}",
    "query": "task: search result | query: {text}",
}

#: Swept rather than assumed, and swept WIDE on purpose. The first version of
#: this bench started at 0.50 and two of the six configurations peaked exactly
#: there: an optimum at the edge of a sweep is not an optimum, it is a sweep that
#: stopped too early. The range now runs from where every space collapses into
#: one cluster to where every space is all singletons, so each peak is interior
#: and the collapse is visible on both sides.
SWEEP = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65,
         0.70, 0.75, 0.80, 0.85, 0.90, 0.95)


def sweep_grid(step: float) -> tuple[float, ...]:
    """The sweep at an arbitrary step, for calibration rather than for reading.

    The default table above is for a human reading a run; choosing a threshold
    to SHIP needs a finer grid, and a value picked off a 0.05 grid would be
    precise to nothing better than 0.05.
    """
    if step >= 0.05:
        return SWEEP
    count = int(round((0.95 - 0.30) / step)) + 1
    return tuple(round(0.30 + step * i, 4) for i in range(count))

#: Tokens per text. EmbeddingGemma takes 2048; an episode opener is a sentence,
#: and a cap keeps the padding of a batch from dominating the run.
MAX_TOKENS = 256
BATCH = 16


class OnnxEmbedder:
    """EmbeddingGemma-300m over onnxruntime, normalising at this boundary.

    Deliberately NOT in `cle/detect/embedders.py`. An embedder in the engine is
    a space the engine's figures can be conditioned on, which requires a
    calibrated threshold and a provenance string that other runs can trust.
    This one is a candidate under measurement; promoting it before the numbers
    exist is how an uncalibrated space ends up inside a lifecycle decision.
    """

    def __init__(self, model_dir: pathlib.Path, variant: str, template: str) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        graph = model_dir / "onnx" / f"model_{variant}.onnx"
        if not graph.exists():
            raise FileNotFoundError(
                f"{graph} is missing. Pass --model-dir pointing at a directory that "
                f"holds onnx/model_{variant}.onnx (and its .onnx_data) plus tokenizer.json; "
                "see this module's docstring for the download command."
            )
        self._session = ort.InferenceSession(str(graph), providers=["CPUExecutionProvider"])
        self._tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self._tokenizer.enable_padding()
        self._template = PROMPT_TEMPLATES[template]
        self.embedder_id = f"onnx:embeddinggemma-300m-{variant}:{template}:768"

    def embed_all(self, texts: Sequence[str]) -> dict[str, tuple[float, ...]]:
        """One forward pass per batch, in the order given; returns text -> vector."""
        import numpy as np

        out: dict[str, tuple[float, ...]] = {}
        distinct = list(dict.fromkeys(texts))
        for start in range(0, len(distinct), BATCH):
            chunk = distinct[start:start + BATCH]
            encoded = self._tokenizer.encode_batch(
                [self._template.format(text=t) for t in chunk]
            )
            ids = np.array([e.ids for e in encoded], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            vectors = self._session.run(
                ["sentence_embedding"], {"input_ids": ids, "attention_mask": mask}
            )[0]
            for text, vector in zip(chunk, vectors):
                # Normalised HERE, explicitly, at the boundary this file owns.
                # `cosine` in the engine is a raw dot product and is a cosine
                # only on unit vectors; the model's own output norm is reported
                # below rather than assumed, because assuming it is exactly how
                # BigQuery's 0.58-norm vectors once produced plausible numbers
                # from an unrelated geometry.
                norm = math.sqrt(float(np.dot(vector, vector)))
                unit = tuple(float(x) / norm for x in vector) if norm else tuple(
                    float(x) for x in vector)
                out[text] = unit
        return out

    def raw_norms(self, texts: Sequence[str]) -> list[float]:
        """The norms the model returns, before this class normalises them."""
        import numpy as np

        encoded = self._tokenizer.encode_batch(
            [self._template.format(text=t) for t in texts[:BATCH]]
        )
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        vectors = self._session.run(
            ["sentence_embedding"], {"input_ids": ids, "attention_mask": mask}
        )[0]
        return [float(np.linalg.norm(v)) for v in vectors]


def _episodes(history: pathlib.Path) -> list:
    """Segment a history with the ENGINE's detector, not a reimplementation.

    What level 1 embeds is an episode opener; a bench that embedded raw messages
    would be measuring a different object than the one the engine clusters.
    """
    records = [json.loads(line) for line in history.read_text().splitlines() if line.strip()]
    messages = [
        Message(**{k: r.get(k) for k in
                   ("text", "ts", "thread_id", "user_id", "requires_tool", "tool_result")})
        for r in records
    ]
    return segment(messages, DetectorConfig())


def openers_with_intents(corpus: str) -> list[tuple[str, str]]:
    """Episode openers with their planted intent, for one corpus.

    `gdg` is IN-SAMPLE for the reference space: 0.775 was swept on these very
    fixtures, so the reference is being read at a threshold this corpus helped
    choose. `holdout` is the process-independent one (`make_holdout.py` imports
    nothing from `cle`), which is why both are offered and why a verdict drawn
    from `gdg` alone would be worth little.
    """
    if corpus not in CORPORA:
        # No silent fallback. This function is imported by the notebook, where
        # the corpus comes from a dropdown; a misspelling that quietly returned
        # the other corpus would relabel every figure drawn from it.
        raise ValueError(f"unknown corpus {corpus!r}; known: {sorted(CORPORA)}")
    if corpus == "gdg":
        if not GDG_HISTORY.exists() or not GROUND_TRUTH.exists():
            raise SystemExit(
                f"{GDG_HISTORY.name} or {GROUND_TRUTH.name} is missing; regenerate both with "
                "`uv run python examples/make_gdg_fixture.py` (offline, free)."
            )
        planted = set(json.loads(GROUND_TRUTH.read_text())["planted_intents"])
        return [(e.messages[0].text, label)
                for e in _episodes(GDG_HISTORY)
                if (label := e.messages[0].thread_id.split("-")[0]) in planted]

    if not HOLDOUT_HISTORY.exists():
        raise SystemExit(
            f"{HOLDOUT_HISTORY.name} is missing; regenerate it with "
            "`uv run python examples/make_holdout.py` (offline, free)."
        )
    return [(e.messages[0].text, label)
            for e in _episodes(HOLDOUT_HISTORY)
            if (label := e.messages[0].thread_id.split("-")[0]) != HOLDOUT_NOISE]


def purity_completeness(assigned: Sequence[int], intents: Sequence[str]) -> tuple[float, float]:
    """Both, because either alone is a trap.

    Purity rewards splitting (one opener per cluster is perfectly pure and says
    nothing); completeness rewards merging (one cluster is perfectly complete).
    `discover_intents.py` documents the same pair for level 2.
    """
    by_cluster: dict[int, list[str]] = {}
    by_intent: dict[str, list[int]] = {}
    for cluster, intent in zip(assigned, intents):
        by_cluster.setdefault(cluster, []).append(intent)
        by_intent.setdefault(intent, []).append(cluster)
    pure = sum(Counter(v).most_common(1)[0][1] for v in by_cluster.values())
    whole = sum(Counter(v).most_common(1)[0][1] for v in by_intent.values())
    return pure / len(assigned), whole / len(assigned)


def adjusted_rand(a: Sequence[int], b: Sequence[int]) -> float:
    """Agreement between two clusterings of the SAME items, chance-corrected.

    Written out rather than imported: `sklearn` is not a dependency of this
    repository and one figure does not justify becoming one.
    """
    pairs: Counter[tuple[int, int]] = Counter(zip(a, b))
    rows, cols = Counter(a), Counter(b)
    comb = lambda n: n * (n - 1) / 2            # noqa: E731 - local, one use
    index = sum(comb(n) for n in pairs.values())
    expected = sum(comb(n) for n in rows.values()) * sum(comb(n) for n in cols.values()) / comb(
        len(a))
    maximum = (sum(comb(n) for n in rows.values()) + sum(comb(n) for n in cols.values())) / 2
    return (index - expected) / (maximum - expected) if maximum != expected else 1.0


def similarity_spread(vectors: dict[str, tuple[float, ...]], texts: Sequence[str],
                      intents: Sequence[str]) -> dict[str, float]:
    """Same-intent against cross-intent cosine: the separation a threshold cuts."""
    same, cross = [], []
    for (i, j) in itertools.combinations(range(len(texts)), 2):
        dot = sum(x * y for x, y in zip(vectors[texts[i]], vectors[texts[j]]))
        (same if intents[i] == intents[j] else cross).append(dot)
    quantile = lambda xs, q: sorted(xs)[min(len(xs) - 1, int(q * len(xs)))]  # noqa: E731
    return {
        "same_median": quantile(same, 0.5), "same_p05": quantile(same, 0.05),
        "cross_median": quantile(cross, 0.5), "cross_p95": quantile(cross, 0.95),
        "gap": quantile(same, 0.5) - quantile(cross, 0.95),
    }


def sweep(vectors: dict[str, tuple[float, ...]], space_id: str, texts: Sequence[str],
          intents: Sequence[str],
          grid: Sequence[float] = SWEEP) -> list[dict[str, float | int | list[int]]]:
    """The engine's own `group()` at each threshold. One row per threshold."""
    space = Precomputed(vectors, space_id)
    rows = []
    for threshold in grid:
        assigned = group(list(texts), space, threshold)
        purity, completeness = purity_completeness(assigned, intents)
        f = (2 * purity * completeness / (purity + completeness)) if purity + completeness else 0.0
        rows.append({
            "threshold": threshold, "clusters": len(set(assigned)),
            "singletons": sum(1 for c, n in Counter(assigned).items() if n == 1),
            "purity": purity, "completeness": completeness, "f": f,
            "assignment": assigned,
        })
    return rows


def _print_sweep(name: str, rows: Iterable[dict]) -> None:
    print(f"\n  {name}")
    print("    threshold  clusters  singletons  purity  completeness      F")
    for row in rows:
        print(f"    {row['threshold']:9.2f}  {row['clusters']:8d}  {row['singletons']:10d}  "
              f"{row['purity']:6.0%}  {row['completeness']:12.0%}  {row['f']:5.3f}")


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=pathlib.Path,
                        help="Directory holding onnx/model_<variant>.onnx and tokenizer.json.")
    parser.add_argument("--variant", default="fp16",
                        help="Quantisation, part of the space id (fp16, fp32, q4f16, ...).")
    parser.add_argument("--template", default="clustering", choices=sorted(PROMPT_TEMPLATES),
                        help="EmbeddingGemma task prefix, also part of the space id.")
    parser.add_argument("--sweep-step", type=float, default=0.05,
                        help="Threshold grid step; below 0.05 prints a finer sweep, which is "
                             "what choosing a value to ship needs.")
    parser.add_argument("--corpus", default="holdout", choices=CORPORA,
                        help="holdout = process-independent (the default, and the only one "
                             "the reference space was NOT calibrated on); gdg = in-sample.")
    args = parser.parse_args()

    print(f"corpus: {args.corpus}"
          f"{' (IN-SAMPLE for the reference threshold 0.775)' if args.corpus == 'gdg' else ''}")
    pairs = openers_with_intents(args.corpus)
    texts = [t for t, _ in pairs]
    intents = [i for _, i in pairs]
    print(f"{len(texts)} episode openers carrying {len(set(intents))} planted intents "
          f"({Counter(intents).most_common()})")

    # ── the reference space: committed, paid for once, offline ────────────────
    cached = CachedEmbedder.from_file()
    reference: dict[str, tuple[float, ...]] = {}
    missing = 0
    for text in dict.fromkeys(texts):
        try:
            reference[text] = tuple(cached.embed(text))
        except Exception:
            missing += 1
    print(f"\nreference space {cached.embedder_id}: {len(reference)} of "
          f"{len(set(texts))} openers in the committed cache ({missing} absent)")
    if missing:
        log.warning("%d opener(s) are not in the committed cache; the comparison runs on "
                    "the intersection", missing)

    # ── the candidate space: local, free, under measurement ──────────────────
    embedder = OnnxEmbedder(args.model_dir, args.variant, args.template)
    started = time.perf_counter()
    candidate = embedder.embed_all(texts)
    elapsed = time.perf_counter() - started
    norms = embedder.raw_norms(texts)
    print(f"candidate space {embedder.embedder_id}: {len(candidate)} openers in "
          f"{elapsed:.1f}s ({elapsed / max(1, len(candidate)) * 1000:.0f} ms each, CPU)")
    print(f"  norms as the model returns them: min {min(norms):.6f} max {max(norms):.6f} "
          f"-> {'already unit' if abs(max(norms) - 1) < 1e-3 else 'NOT unit, normalised here'}")
    for text in list(candidate)[:32]:
        assert_unit_norm(candidate[text], where=f"{embedder.embedder_id} after normalisation")
    assert_batch_varied([str(candidate[t][:4]) for t in candidate],
                        label=embedder.embedder_id)

    shared = [t for t in texts if t in reference]
    shared_intents = [i for t, i in pairs if t in reference]
    print(f"\nboth spaces hold {len(shared)} of {len(texts)} openers; "
          "every figure below is on that intersection")

    for name, vectors in (("reference " + cached.embedder_id, reference),
                          ("candidate " + embedder.embedder_id, candidate)):
        spread = similarity_spread(vectors, shared, shared_intents)
        print(f"\n  {name}")
        print(f"    same-intent cosine   median {spread['same_median']:+.4f}  "
              f"p05 {spread['same_p05']:+.4f}")
        print(f"    cross-intent cosine  median {spread['cross_median']:+.4f}  "
              f"p95 {spread['cross_p95']:+.4f}")
        print(f"    separation (same median - cross p95) {spread['gap']:+.4f}")

    grid = sweep_grid(args.sweep_step)
    rows_ref = sweep(reference, cached.embedder_id, shared, shared_intents, grid)
    rows_new = sweep(candidate, embedder.embedder_id, shared, shared_intents, grid)
    _print_sweep("reference " + cached.embedder_id, rows_ref)
    _print_sweep("candidate " + embedder.embedder_id, rows_new)

    best_ref = max(rows_ref, key=lambda r: r["f"])
    best_new = max(rows_new, key=lambda r: r["f"])
    calibrated = CLUSTER_THRESHOLD_BY_EMBEDDER.get(cached.embedder_id)
    print(f"\nbest F: reference {best_ref['f']:.3f} at {best_ref['threshold']:.2f} "
          f"(the table ships {calibrated}), candidate {best_new['f']:.3f} at "
          f"{best_new['threshold']:.2f}")
    print("agreement between the two clusterings, each at its own best threshold: "
          f"adjusted Rand index {adjusted_rand(best_ref['assignment'], best_new['assignment']):+.3f}")
    print("\nNeither number ranks a space: a space is readable only at its own calibrated "
          "threshold, and the two partitions differ even where the scores are close.")
    if args.corpus == "gdg":
        print("This corpus is IN-SAMPLE for the reference's 0.775, which was swept on these "
              "fixtures; `--corpus holdout` is the process-independent comparison.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
