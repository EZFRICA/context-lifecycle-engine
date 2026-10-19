# Working in this repository

Reference implementation of the Agent OS series. The research question is the
**lifecycle value of agents that already exist**, so the deliverable is always
architectures with their trade-offs, **never a winner**.

Detail lives in skills, which load when they apply, rather than here:

| task | skill |
|---|---|
| store, build, runtime, lifecycle, invariants, log lines | `cle-core-contracts` |
| replay, episodes, clusters, embedders, signals, stability | `replay-validation` |
| any number, bench, threshold, figure or comparison | `cle-measurement-discipline` |
| logs, exception messages, prompts, reports, anything published | `cle-text-boundaries` |
| the FastAPI dashboard and its routes | `cle-dashboard` |
| CSS, markup, colours for the dashboard | `cle-visual-identity` |

`docs/BLUEPRINT.md` is the contract; §10 lists what it does **not** promise.

## True for every change

- **`.cle/` is never touched by tooling.** It holds the only copy of a real
  oplog, store and topology history, and it is gitignored, so git cannot
  restore it. Benches, demos and the dashboard run on a scratch state dir.
- **Docs describe the code at time T.** No "previously", no changelog prose;
  history belongs in the gitignored `EVOLUTION.md`.
- **A number carries its pinning key and the command that reproduces it**, and
  a new measurement is published beside the old one, never over it.
- **No test needs a key or the network.** The suite is offline by construction;
  `RealEmbedder` may not be imported by any test module.
- **A new guard ships with a test that goes red when the guard is removed** -
  per raise site, not per exception class.

## The verification series

```bash
uv run pytest -q                              # the suite; it also guards the documented counts
GITHUB_ACTIONS=true uv run pytest -q          # Typer forces Rich mode in CI; three tests once failed only there
uv run python tools/buckets.py --check        # the test buckets are measured, not counted
uv run --with pyrefly pyrefly check --min-severity warn
CLE_MODEL_A=stub-model-a CLE_MODEL_B=stub-model-b bash examples/full_loop.sh
uv run python tools/mutate.py                 # ALONE: it mutates the tree in place
```

Green offline is not done. A live run (`CLE_FORCE_REAL_MODEL=1`) on a scratch
state has twice found defects nothing offline could see - a test reading the
ambient environment, and a prompt the live model answered by mimicking its
delimiters.

## Licence

Apache-2.0 (`LICENSE`, attribution in `NOTICE`). The corpora are **not** under
it and are not distributed here: Stack Overflow via the BigQuery public dataset
(CC BY-SA), WildChat under AllenAI's terms, every derived file gitignored.
