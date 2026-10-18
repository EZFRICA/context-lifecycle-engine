## 8. A free local space at level 1: EmbeddingGemma-300m through ONNX


`(2026-10-17, 2a997be + uncommitted, onnx:embeddinggemma-300m-fp16:<prefix>:768
against google:gemini-embedding-2:768, no model-id - replay is not involved)`

```bash
uv run --with onnxruntime --with tokenizers python examples/onnx_embedding_bench.py \
    --model-dir <dir> --corpus holdout --template query
```

Bills nothing and calls nothing: the candidate is a local ONNX file, the
reference is the committed cache, the labels are planted. Both corpora are
offline fixtures; `holdout` is the process-independent one, `gdg` is IN-SAMPLE
for the reference's calibrated 0.775.

Best F (purity and completeness balanced), each space read at **its own** best
threshold over a 0.30-0.95 sweep:

| prefix | corpus | reference | candidate | agreement (ARI) |
|---|---|---:|---:|---:|
| `clustering` | holdout | 0.924 @ 0.70 | 0.665 @ 0.85 | +0.270 |
| `clustering` | gdg | 0.785 @ 0.75 | 0.580 @ 0.85 | +0.208 |
| `document` | holdout | 0.924 @ 0.70 | 0.800 @ 0.40 | +0.384 |
| `document` | gdg | 0.785 @ 0.75 | 0.780 @ 0.60 | +0.503 |
| `query` | holdout | 0.924 @ 0.70 | **0.904 @ 0.40** | +0.646 |
| `query` | gdg | 0.785 @ 0.75 | **0.897 @ 0.50** | +0.530 |

**THE TASK PREFIX IS A COORDINATE OF THE SPACE, and it moves F by as much as the
model choice does.** EmbeddingGemma is trained with task prefixes; the same
openers under `task: clustering` and under `task: search result` are different
embeddings. The prefix that NAMES the task at hand is the worst of the three
here (0.58-0.67), and `query` is the best (0.90). Anyone reporting a number for
this model without naming its prefix has reported a number for one of three
spaces, chosen by accident.

**The threshold travels with the space, again.** 0.6 for the bag-of-tokens stub,
0.775 for `gemini-embedding-2`, **0.40-0.50** for this one under `query`. Its
cosines sit higher across the board (cross-intent median 0.71-0.73 against
0.61), so a threshold borrowed from the reference would put this space in its
all-singletons regime.

**Scores close, partitions not.** At their respective best thresholds the two
spaces agree at ARI +0.646 on the holdout - well above chance, far from the same
answer. A space that scores alike is not a space that groups alike, which is why
`cle population` records `embedder_id` with every figure it writes.

**What this does NOT say.** Not that one space is better: 27 and 70 distinct
openers are small, both corpora are synthetic fixtures, the sweep grid is 0.05,
and the reference is read at its own best rather than at the 0.775 it ships -
which is generous to the reference. One quantisation (fp16) was measured; the
repository publishes six, and they are six spaces. Nothing here was measured on
real user text, and no figure above licenses a lifecycle decision in this space:
`CLUSTER_THRESHOLD_BY_EMBEDDER` has no entry for it, deliberately, because a
space with no calibrated threshold must not reach a promotion.

**What it does say.** A 622 MB file on CPU, 20-30 ms per opener, no key and no
network, lands within 0.02 F of the paid space on the only corpus neither was
calibrated on. For a deployment whose constraint is that user text must not
leave the machine, that is the measurement that matters, and it did not exist
before.
