# Context Lifecycle Engine (CLE)

> A system that lets useful agents **emerge from how you actually work**, then
> earns or revokes their standing on lived evidence — never on prediction.

Reference implementation of the *Agent OS* series (parts 7–8). The CLE watches a
user's prompt history, detects recurring intents that deserve their own agent,
compiles each candidate into a content-addressed **image**, validates it by
replaying the user's own past, and moves it up and down a lifecycle ladder as
evidence accumulates or expires.

It borrows vocabulary from Docker (build / image / container / volumes /
topology), Git (a Merkle store), and the APU series (block auto-detection,
promoted from memory blocks to whole agents) — but every component has to justify
itself by a CLE need, not by the analogy. `docs/BLUEPRINT.md` is the contract.

---

## The contract — six invariants

These are enforced in code and pinned by property tests. They are the reason the
system is trustworthy:

1. **Two hashes.** A candidate's `SourceSpec.hash` is never its built
   `Image.hash`. Lifecycle tags attach to image hashes only; tagging a source
   raises `TagTargetError`.
2. **Goodhart boundary.** A `Container` exposes **no** read path to its own
   metrics — no method, property, or injected context. Metrics are written
   one-way to a system-owned volume; only the engine and the human read them.
3. **Staged builds consume nothing.** A failed resolve / replay / assemble
   leaves the store byte-identical and writes only the build log line.
4. **Every operation logs one JSON line**, with a mandatory `evidence` field on
   any upward tag move. No log, no merge.
5. **Replay proves the trigger, never the answer.** Replay outputs are
   `PreEvidence` and can never flow into a promotion — yesterday's user cannot
   score an alternative answer.
6. **Proof expires.** Images freeze a `model_fingerprint`; the re-validator can
   demote an agent when the served model drifts.

---

## Install

The project uses [`uv`](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
```

## Configuration

`cle build`, `cle run`, and `cle revalidate` call the LLM configured in `.env`
(Gemini by default) on their **live path**. The test suite and the reproducible
parts of the demo use a deterministic `StubFingerprinter`, so **no key is
required to run the tests** or to understand the numbers.

```bash
cp .env.example .env   # then fill in GEMINI_API_KEY
```

`.env` is gitignored — never commit real keys. See `.env.example` for every
recognized variable (LLM provider, Ollama fallback, actor label, optional
Weaviate backend).

The live fingerprint probes run at **temperature 0** (greedy decoding), so the
same model yields the same footprint and a fingerprint delta means the *model*
actually drifted — not that the sampler rolled differently.

---

## Quick start

```bash
# 1. Generate synthetic history; the DETECTOR writes the candidate agent yaml.
uv run python examples/make_fixture.py

# 2. Three-stage build (resolve -> replay-validate -> assemble); prints the
#    capture / false-trigger / historical-cost numbers and the two hashes.
uv run cle build examples/weekly_recap_agent.yaml \
  --replay-window 35d --history examples/prompt_history_adversarial.jsonl

# 3. Instantiate the agent in two workspaces and solicit it.
uv run cle run weekly_recap --workspace alpha --prompts 2
uv run cle run weekly_recap --workspace beta  --prompts 4

# 4. Divergent per-container metrics (read across the Goodhart boundary).
uv run cle ps

# 5. Promote on lived evidence; the shadow engine judges the same evidence.
uv run cle tag weekly_recap trial
uv run cle tag weekly_recap ephemeral \
  --cost-ratio 0.6 --occurrences 4 --closures success,success,success,success

# 6. Topology history and the learned-topology delta.
uv run cle log topology.yaml
uv run cle diff topology/v1 topology/v3

# 7. Revalidate under a drifted model — proof expires, agent auto-demotes.
uv run cle revalidate weekly_recap --model-id drifted-model-2
```

### The whole loop in one script

```bash
bash examples/full_loop.sh
```

It cleans state, regenerates fixtures, builds with replay (a deliberately
adversarial window yields a **non-trivial** `false_trigger_rate ≈ 0.043`), runs
two workspaces, shows a container **switch** with its `diff_blocks` / `diff_tokens`
cost, promotes and pins the agent while the shadow engine logs what it *would*
do, diffs two topology versions, and finally drifts the model to trigger an
auto-demotion. Ends with the full test suite.

### Live dashboard

```bash
uv run cle dashboard --port 8000   # http://localhost:8000
```

A single-page dashboard over the persistent `.cle/` state: agent cards, running
workspaces with live metrics, the topology, and a tail of the op-log stream. It
reads `/api/state` and triggers `run` / `tag` / `revalidate` through the CLI.

---

## CLI reference

The CLI operates on a persistent state directory (`--state-dir`, default `.cle/`).

| Command | What it does |
|---|---|
| `cle build <src.yaml>` | Resolve → replay-validate → assemble; births the candidate (tag + topology). `--replay-window`, `--history`, `--components`. |
| `cle run <agent> --workspace <ws>` | Instantiate (or switch) the workspace's container and solicit it. `--prompts N`. |
| `cle ps` | Containers and their per-container metrics (solicitations, iterations, closures). |
| `cle tag <agent> <state>` | Move a state tag (`--cost-ratio`, `--occurrences`, `--closures`, `--reason`); the shadow engine judges the same evidence. |
| `cle log [topology.yaml]` | Op-log tail, or topology history with provenance and numbers. |
| `cle diff <vA> <vB>` | Learned-topology delta between two versions (e.g. `topology/v1 topology/v5`). |
| `cle revalidate <agent>` | Replay the frozen probe set; on drift, auto-demote to `trial`. `--model-id`. |
| `cle dashboard` | Launch the web dashboard. `--port`. |
| `cle clean` | Reset the `.cle/` state directory. |

---

## Architecture

### Two pillars
- **Detection** — episodes are segmented (silence threshold + explicit markers),
  their openers embedded and clustered, and per-cluster signals
  (reformulation / recurrence) counted against a **per-user baseline**, never an
  absolute threshold. A cold user (< 14 days / < 20 episodes) gets no candidates;
  the detector observes silently.
- **Lifecycle** — candidates are built, trialed, promoted, demoted, archived,
  resurrected, and re-validated — evidence-driven throughout.

### Three-stage build
1. **Resolve** — every `#ref` exists and re-hashes to its address, or the build
   fails in milliseconds having written nothing.
2. **Replay-validate** — re-segment the window, route it against the topology
   *plus* the candidate, and report `capture_rate`, `false_trigger_rate`
   (out-of-cluster traffic is replayed too), and `historical_cost`. These are
   `PreEvidence` and gate the build only.
3. **Assemble** — compile the prompt in declared order, freeze the probe set and
   `model_fingerprint`, and hash the artifact into an `Image`.

### Seven-state ladder
```
archived(0)  ↔  candidate(1)  ↔  trial(2)  ↔  ephemeral(3)  ↔  pinned(4)
```
- **`ephemeral`** — promoted on lived `Evidence` (occurrences + cost ratio).
- **`pinned`** — stable over ≥ 10 solicitations at non-worsening cost (engine
  rule, config; the W-day window is documented intent, not yet enforced in v1).
- **Shadow engine** — runs the part-7 thresholds (article defaults: promote at
  cost ≤ 0.7, silence-demote past 2× the pattern's period) and logs
  `actor:"engine:shadow"` with what it *would* do. It never writes a ref in v1;
  the human/engine divergence log is the calibration set for going live.

### Three standards of proof
`PreEvidence` (replay, retrospective) · `Evidence` (trial, lived) ·
`Persistence` (re-validation, drift) are **distinct types**. A function that
wants `Evidence` rejects the other two at type level — replay numbers can never
be smuggled into a promotion.

### Store & runtime
Content-addressed store behind a `Protocol` — `InMemoryStore` (default, the only
test dependency), `FileStore` (persistent CLI state), and an optional
`WeaviateStore`. `topology.yaml` is written only by `lifecycle/topology.py`;
every change is a store commit under `topology/v<n>` carrying its cause.

---

## Repository layout

```
cle/
  store/        objects (content_hash, Block) · commits (SourceSpec, Image,
                evidence types) · backends (Protocol, InMemory, File)
  detect/       episodes · clusters · signals
  build/        resolver · replay · assembler
  runtime/      container · mounts · metrics_volume
  lifecycle/    tags · engine (shadow) · topology · revalidator
  cli/          main.py (typer)
  ui/           web dashboard
examples/       make_fixture.py · full_loop.sh · fixtures & components
docs/           BLUEPRINT.md (the contract) · METRICS.md (what the numbers mean)
tests/          property/ + unit/ — hypothesis for the invariants
```

## Testing

```bash
uv run pytest -q
```

Property + unit tests enforce every invariant — two-hash inequality, staged-
failure-writes-nothing, the Goodhart reflection test, `PreEvidence`/`Evidence`
type separation, build determinism, and probe-set hash coverage. **No test
requires Weaviate or a network call.**

---

## Status

P1–P3 of the v1 blueprint are implemented: two-hash store, three-stage build with
replay validation, the minimal detector, the container runtime with switch-cost
logging, the seven-state lifecycle with a shadow engine, the topology writer, and
the re-validator — plus a live-LLM integration and a web dashboard. See
`docs/METRICS.md` for exactly what each number the demo prints does and does not
prove, and `docs/BLUEPRINT.md` for the governing contract.
