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
promoted from memory blocks to whole agents) — but every component has to
justify itself by a CLE need, not by the analogy. `docs/BLUEPRINT.md` is the
contract.

---

## Measured reality (read this before any number below)

The mechanisms described here are implemented and tested. **How well detection
recovers real usage is a separate, measured question**, and the honest answers
are unflattering. Three measurement runs found:

1. **v1 detection only worked because the fixtures were templated.** The
   original fixtures repeated one identical opener per intent. Rebuilt with
   genuinely varied human phrasing, the v1 bag-of-tokens embedder (cosine 0.6)
   shattered every recurring intent into near-singletons — 63 clusters for 7
   planted intents — and holdout discovery fell to **0**.

2. **A real embedding model helps, but is not a drop-in.** At the old 0.6
   threshold `google:gemini-embedding-2:768` fails the *opposite* way —
   over-merging everything into 2 clusters, with `false_trigger` jumping
   **0.061 → 0.632** (events intent, ideal centroid). Recalibrated to
   **0.775** (scoped to `embedder_id`) it beats v1, but GDG recovery still tops
   out at **2/7** planted intents, and of the 6 candidates it births only
   **2 are genuine** (2 pure fragments, 2 spurious — including a 20-episode
   noise agglomerate).

3. **It breaks contradiction detection outright.** Cosine measures *topical
   relatedness, not contradiction*: the planted **opposing** directives score
   0.62–0.86 because they *are* about the same thing. The contradiction
   classifier now returns **`unavailable`** in such a space — a disclosed gap
   carried to the human gate, never a reassuring "stable".

Numbers attributed to `weekly_recap` / `standup_digest` / `incident_triage` and
to `examples/full_loop.sh` come from the **legacy templated demo source**
(`make_fixture.py`, not yet de-templated). `docs/METRICS.md` organises every
figure into three eras (A legacy demo / B realistic data / C real embedder =
current) with per-number provenance.

---

## The contract — six invariants

Enforced in code and pinned by property tests. They are the reason the system is
trustworthy:

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
6. **Proof expires.** Images freeze a `model_fingerprint`; the re-validator
   demotes an agent when the served model drifts.

A seventh rule, added after measurement: **a non-measurement is never a
verdict.** A check that cannot run in the configured vector space reports
`unavailable` and the gap is disclosed — it is never silently treated as a pass.

---

## Install

The project uses [`uv`](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
```

## Configuration

`cle build`, `cle run`, and `cle revalidate` call the LLM configured in `.env`
(`gemini-3.5-flash-lite` by default) on their **live path** — that is the
default locally, so the system runs on a real substrate. The **test suite** uses
deterministic stub fingerprinters and a **committed vector cache** for the
detection embedder, so **no key is required to run the tests** or to reproduce
the replay numbers. Any command's substrate can be pinned with `--model-id`
(`current` / a real model name / `stub-*`).

```bash
cp .env.example .env   # then fill in GEMINI_API_KEY
```

`.env` is gitignored — never commit real keys. See `.env.example` for every
recognized variable (LLM provider, Ollama fallback, actor label).

The live fingerprint probes run at **temperature 0** (greedy decoding), so the
same model yields the same footprint and a fingerprint delta means the *model*
actually drifted — not that the sampler rolled differently.

---

## Quick start

```bash
# 1. Generate the LEGACY TEMPLATED demo history; the DETECTOR writes one agent
#    yaml per pattern (weekly_recap, standup_digest, incident_triage) plus a
#    hand-authored status_report incumbent.
uv run python examples/make_fixture.py

# 2. Three-stage build (resolve -> replay-validate -> assemble); prints the
#    capture / false-trigger / historical-cost numbers and the two hashes.
#    capture_rate is measured against the CURRENT topology: build status_report
#    first and weekly_recap drops to 0.60 because the incumbent already owns
#    two of its episodes.
uv run cle build examples/weekly_recap_agent.yaml \
  --replay-window 40d --history examples/prompt_history_adversarial.jsonl

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
./examples/full_loop.sh                          # the file is executable
bash examples/full_loop.sh                       # or explicitly
uv run examples/full_loop.sh                     # or through uv
CLE_STORE=sqlite ./examples/full_loop.sh         # or with sqlite backend
```

Runs on **real models by default**; force an offline deterministic run with
`CLE_MODEL_A=stub-model-a CLE_MODEL_B=stub-model-b ./examples/full_loop.sh`
(what CI does). Add `CLE_STORE=sqlite` to run the whole loop on the sqlite
backend instead of the default file store.

Twelve steps: regenerate fixtures, build four agents (`weekly_recap` lands at
capture **0.60** — the `status_report` incumbent owns
two of its episodes), replay against a deliberately adversarial window
(`false_trigger ≈ 0.081` — one bridge fires, four near-miss traps rejected), run
two workspaces, show a real container **switch** cost (`Δ 4 blocks · 127
tokens`), promote to `pinned` while the shadow engine logs a genuine
**divergence**, demote on regression, fire an **integrity violation**, expire
proof under a drifted substrate, rebuild a **v2 born from that drift**, and end
with the test suite. *All era-A figures — the source is templated.*

### Live dashboard

```bash
uv run cle dashboard --port 8000                  # http://localhost:8000
uv run cle --store sqlite dashboard --port 8000   # if the CLI wrote sqlite
```

A single page (HTML + Alpine, no build step) over the persistent `.cle/` state,
served by FastAPI. Four zones — **Pulse** (live oplog over SSE), **Births**
(candidate cards with the human Approve/Decline gate, and the disclosed-gap
marker when the contradiction check could not run), **Lives**, **Topology**. The
**only** write path is Approve/Decline, routed through the `cle` CLI and logged
as `human:dashboard`. See `dashboard/README.md`.

---

## CLI reference

The CLI operates on a persistent state directory (`--state-dir`, default `.cle/`).

**Global option — goes BEFORE the subcommand:**

```bash
uv run cle --store sqlite build ...      # or: export CLE_STORE=sqlite
uv run cle --store sqlite dashboard      # NOT `uv run cle dashboard --store sqlite`
```

`--store {file,sqlite}` selects the persistence backend (default `file`, or
`$CLE_STORE`). The two hold **different paths** under the state dir —
`.cle/store/` vs `.cle/store.db` — so switching starts an empty store rather
than half-reading the other. The dashboard reads whatever the CLI wrote only
if it is launched with the same setting; that is why the flag is global.

| Command | What it does |
|---|---|
| `uv run cle build <src.yaml>` | Resolve → replay-validate → assemble; births the candidate (tag + topology). Replays against the current topology, so incumbents compete. `--replay-window`, `--history`, `--components`, `--model-id`. |
| `uv run cle run <agent> --workspace <ws>` | Instantiate (or switch) the workspace's container and solicit it. `--prompts N`. |
| `uv run cle ps` | Containers and their per-container metrics (solicitations, iterations, closures). |
| `uv run cle tag <agent> <state>` | Move a state tag (`--cost-ratio`, `--occurrences`, `--closures`, `--reason`); the shadow engine judges the same evidence. |
| `uv run cle log [topology.yaml]` | Op-log tail, or topology history with provenance and numbers. |
| `uv run cle diff <vA> <vB>` | Learned-topology delta between two versions. |
| `uv run cle revalidate <agent>` | Replay the frozen probe set; on drift, auto-demote to `trial`. `--model-id`. |
| `uv run cle decline <agent>` | Refuse a candidate — logs the refusal, moves no tag. `--reason`. |
| `uv run cle dashboard` | Launch the FastAPI dashboard. `--port`. |
| `uv run cle clean` | Reset the `.cle/` state directory. |

---

## Architecture

### Two pillars
- **Detection** — episodes are segmented (silence threshold + explicit markers),
  their openers embedded and clustered, and per-cluster signals
  (reformulation / recurrence) counted against a **per-user baseline**, never an
  absolute threshold. A cold user (< 14 days / < 20 episodes) gets no
  candidates; the detector observes silently.
- **Lifecycle** — candidates are built, trialed, promoted, demoted, archived,
  resurrected, and re-validated — evidence-driven throughout.

### Three-stage build
1. **Resolve** — every `#ref` exists and re-hashes to its address, or the build
   fails in milliseconds having written nothing. Declared tools must resolve and
   the trigger's required capability must be mounted.
2. **Replay-validate** — re-segment the window, route it against the topology
   *plus* the candidate, and report `capture_rate`, `false_trigger_rate`
   (out-of-cluster traffic is replayed too) and `historical_cost`. These are
   `PreEvidence` and gate the build only.
3. **Assemble** — compile the prompt in declared order, freeze the probe set and
   `model_fingerprint`, and hash the artifact into an `Image`.

### The embedder is a substrate
Clustering runs behind an `Embedder` Protocol with three implementations: the
live `RealEmbedder` (generation-only, the sole thing needing a key), the
`CachedEmbedder` over committed vectors (**the suite default** — a cache miss is
an error, never a live call), and the deterministic `StubEmbedder`.

`TriggerSpec` records `embedder_id`, and `Image.hash` covers the trigger, so
**two images built on different embedders have different hashes**: a centroid is
only meaningful inside the space that produced it, and an embedder swap
invalidates centroids exactly as a model swap invalidates a fingerprint — one
layer deeper, and this one touches agent **identity**. Cross-space comparison
raises. The clustering **threshold travels with `embedder_id`** (0.6 for the
stub, 0.775 for the real embedder); one number cannot serve both spaces.

### Lifecycle ladder — five states in v1
```
archived(0)  ↔  candidate(1)  ↔  trial(2)  ↔  ephemeral(3)  ↔  pinned(4)
```
- **`ephemeral`** — promoted on lived `Evidence` (occurrences + cost ratio).
- **`pinned`** — stable over ≥ 10 solicitations at non-worsening cost.
- **Shadow engine** — runs the part-7 thresholds and logs what it *would* do. It
  never writes a ref in v1; the human/engine divergence log is the calibration
  set for going live.

### Three standards of proof
`PreEvidence` (replay, retrospective) · `Evidence` (trial, lived) ·
`Persistence` (re-validation, drift) are **distinct types**. A function that
wants `Evidence` rejects the other two at type level — replay numbers can never
be smuggled into a promotion.

### Store & runtime
Content-addressed store behind a `Protocol` — `InMemoryStore` (tests),
`FileStore` (the CLI default) and `SqliteStore` (one inspectable `.cle/store.db`,
opt-in via `--store sqlite`). Every entry point selects through the single
`open_store` factory, so the CLI and the dashboard can never end up on
different backends. A remote `WeaviateStore` is **deferred, not implemented**.
`topology.yaml` is written only by `lifecycle/topology.py`; every change is a
store commit under `topology/v<n>` carrying its cause.

---

## Repository layout

```
cle/
  store/        objects (content_hash, Block) · commits (SourceSpec, Image,
                TriggerSpec, evidence types) · backends (InMemory/File/Sqlite)
  detect/       episodes · clusters · embedders (+ provenance) · signals ·
                stability (intra-cluster divergence)
  build/        resolver · replay · assembler · fingerprinter (live substrate)
  runtime/      container · mounts · metrics_volume
  lifecycle/    tags · engine (shadow) · topology · revalidator
  cli/          main.py (typer)
dashboard/      backend/ (FastAPI + SSE) · frontend/ (HTML + Alpine)
examples/       make_fixture.py (legacy templated ground truth + adversarial) ·
                make_gdg_fixture.py (realistic) · make_holdout.py (independent
                discovery) · make_vectors.py (offline embedding cache) ·
                phrasing.py · full_loop.sh · gdg_demo.py · committed histories
docs/           BLUEPRINT.md (the contract) · METRICS.md (per-number
                provenance) · CAPABILITIES.md (what the system does)
tests/          property/ + unit/ — hypothesis for the invariants
```

## Testing

```bash
uv run pytest -q
```

**225 tests across 26 files** (+1 opt-in Weaviate integration test, skipped by
default). **No test requires Weaviate, an API key, or a network call** — the
detection embedder is a committed vector cache, a miss is an error rather than a
live call, and a test asserts that no test module imports the live embedder.

### What a green suite does and does not mean

Classified by what each assertion actually depends on:

| Bucket | Tests | Meaning |
|---|---|---|
| **Embedder-agnostic** | **136** | No embedder in the assertion. The invariant core — hashing, store, integrity, evidence types, Goodhart, staged failure, lifecycle, segmentation, signals, fixture data properties. Holds in **any** era. |
| **Stub-as-a-tool** | **58** | Needs *some* deterministic embedder, but the claim is space-independent (two-hash inequality, build determinism, both rates computed, tool gating, provenance). |
| **Stub-as-the-subject** | **31** | True **only** in `stub:hashed64` — the contradiction taxonomy and the demo's exact rates. These do **not** describe the production system, and every such module carries a SCOPE header saying so. |

The good news is the first row: **136 of 225 assertions are contract-core** and
independent of which embedder is configured.

### Three data sources, three roles

Evaluating a detector on data you generated with that detector's own geometry is
a consistency check, not a discovery test. So the fixtures are split by role:

| Source | Role |
|---|---|
| **ground truth** (`make_gdg_fixture.py`) | planted patterns — the system **recovers** what we know is there |
| **adversarial** (`make_fixture.py`) | one bridge that fires + near-miss traps — the system **does not fire** on what isn't there |
| **holdout** (`make_holdout.py`) | a history written **independently** of the detector (imports nothing from `cle`, never touches the embedder, threshold or centroids) — the system **discovers** unplanted patterns |

The holdout test asserts structural sanity only and **reports** its numbers
without asserting them, in both eras: **0** discoveries with the v1 embedder,
and with the real embedder at its calibrated threshold a pure candidate for all
three patterns — **2 clean recoveries + 1 pure fragment**. That second figure is
the single independent confirmation the 0.775 threshold rests on, so it is now
pinned by a committed test rather than a measurement script.

---

## Status

P1–P3 of the v1 blueprint are implemented: two-hash store, three-stage build
with replay validation, the minimal detector, the container runtime with
switch-cost logging, the five-state lifecycle with a shadow engine, the
topology writer, and the re-validator — plus a live Gemini substrate, a real
embedding substrate behind the Protocol, and the FastAPI dashboard.

Known limits, stated plainly: replay validates the **trigger only**, never
answer quality and never the temporal period; silence-based demotion is a shadow
rule whose data the runtime does not yet track; the lifecycle engine runs in
**shadow mode** (humans move tags); **contradiction detection needs an operator
that is not a distance** (signed / entailment) and is inert until it gets one;
and the adversarial/demo fixture source is **still templated**.

See `docs/METRICS.md` for what each number does and does **not** prove,
`docs/CAPABILITIES.md` for the capability-to-test map, and `docs/BLUEPRINT.md`
for the governing contract.
