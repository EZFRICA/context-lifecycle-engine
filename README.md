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
(`gemini-3.5-flash-lite` by default) on their **live path** — that is the
default locally, so the system runs on a real substrate. The **test suite** uses
deterministic stub fingerprinters internally, and **CI** forces stub substrates
(`CLE_MODEL_A/B=stub-model-*`), so **no key is required to run the tests** or to
reproduce the replay numbers. Any command's substrate can be pinned with
`--model-id` (`current` / a real model name / `stub-*`).

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
# 1. Generate synthetic history; the DETECTOR writes one agent yaml per real
#    pattern (weekly_recap, standup_digest, incident_triage) + a hand-authored
#    status_report incumbent.
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
bash examples/full_loop.sh
```

It runs on **real models by default**; force an offline, deterministic run with
`CLE_MODEL_A=stub-model-a CLE_MODEL_B=stub-model-b bash examples/full_loop.sh`
(this is what CI does). The 12 steps: regenerate fixtures, build four agents
(`weekly_recap` lands at capture **0.60** — the `status_report` incumbent owns
two of its episodes), replay against a deliberately adversarial window
(`false_trigger_rate ≈ 0.081` — one bridge fires, four near-miss traps are
rejected), run two workspaces, show a real container **switch** cost
(`Δ 4 blocks · 127 tokens`), promote to `pinned` while the shadow engine logs
what it *would* do (including a genuine **divergence**), demote on regression,
fire an **integrity violation**, expire proof under a drifted substrate, and
rebuild a **v2 born from that drift**. Ends with the full test suite.

### Live dashboard

```bash
uv run cle dashboard --port 8000   # http://localhost:8000
```

A single page (HTML + Alpine, no build step) over the persistent `.cle/` state,
served by FastAPI from `dashboard/`. Four zones — **Pulse** (live oplog over
SSE), **Births** (candidate cards with the human Approve/Decline gate),
**Lives** (lifecycle chips, per-container metrics, switch-cost badges, the drift
card), **Topology** (state ladder, shadow strip, version diff). Click an agent
for a detail modal. It streams `GET /events` and reads `GET /state/*`; the
**only** write path is Approve/Decline, routed through the `cle` CLI and logged
as `human:dashboard`. See `dashboard/README.md`.

---

## CLI reference

The CLI operates on a persistent state directory (`--state-dir`, default `.cle/`).

| Command | What it does |
|---|---|
| `cle build <src.yaml>` | Resolve → replay-validate → assemble; births the candidate (tag + topology). Replays against the current topology, so incumbents compete. `--replay-window`, `--history`, `--components`, `--model-id`. |
| `cle run <agent> --workspace <ws>` | Instantiate (or switch) the workspace's container and solicit it. `--prompts N`. |
| `cle ps` | Containers and their per-container metrics (solicitations, iterations, closures). |
| `cle tag <agent> <state>` | Move a state tag (`--cost-ratio`, `--occurrences`, `--closures`, `--reason`); the shadow engine judges the same evidence. |
| `cle log [topology.yaml]` | Op-log tail, or topology history with provenance and numbers. |
| `cle diff <vA> <vB>` | Learned-topology delta between two versions (e.g. `topology/v1 topology/v5`). |
| `cle revalidate <agent>` | Replay the frozen probe set; on drift, auto-demote to `trial`. `--model-id` (`current`, a real model name, or `stub-*`). |
| `cle decline <agent>` | Refuse a candidate — logs the refusal, moves no tag. `--reason`. |
| `cle dashboard` | Launch the FastAPI dashboard (`dashboard/`). `--port`. |
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
  build/        resolver · replay · assembler · fingerprinter (live substrate)
  runtime/      container · mounts · metrics_volume
  lifecycle/    tags · engine (shadow) · topology · revalidator
  cli/          main.py (typer)
  llm_provider  Gemini / Ollama routing (temperature 0 for fingerprints)
dashboard/      backend/ (FastAPI + SSE) · frontend/ (HTML + Alpine)
examples/       make_fixture.py (ground truth + adversarial) ·
                make_holdout.py (independent discovery) · full_loop.sh ·
                histories, agents & component blocks
docs/           BLUEPRINT.md (the contract) · METRICS.md (per-number
                provenance) · CAPABILITIES.md (what the system does)
tests/          property/ + unit/ — hypothesis for the invariants
```

## Testing

```bash
uv run pytest -q
```

**219 tests** (property + unit; +1 opt-in Weaviate integration test, skipped by
default) enforce every invariant — two-hash inequality,
staged-failure-writes-nothing, the Goodhart reflection test,
`PreEvidence`/`Evidence` type separation, build determinism, and probe-set hash
coverage. **No test requires Weaviate, an API key, or a network call** (the
detection embedder is a committed vector cache; a cache miss is an error, never
a live call).

### Three data sources, three roles

Evaluating a detector on data you generated with that detector's own geometry is
a consistency check, not a discovery test. So the fixtures are split by role:

| Source | Role |
|---|---|
| **ground truth** (`make_fixture.py`) | planted patterns — the system **recovers** what we know is there |
| **adversarial** (`adversarial_history()`) | one bridge that fires + near-miss traps — the system **does not fire** on what isn't there |
| **holdout** (`make_holdout.py`) | a history written **independently** of the detector (imports nothing from `cle`, never touches the embedder, cosine threshold or centroids) — the system **discovers** unplanted patterns |

The holdout test asserts only structural sanity and **reports** its numbers
without asserting them. What it reports depends on the substrate (see *Measured
findings* below): with the v1 bag-of-tokens embedder on realistic data it
discovers **0**; with the real embedder at its calibrated threshold it produces
a pure candidate for all three patterns, of which **2 are clean recoveries and
1 is a pure fragment** (`docs/METRICS.md`, R10). Documented as-is, not tuned.

---

## Measured findings (read before trusting any number)

The quick-start and `full_loop.sh` numbers above (`weekly_recap` capture 0.60,
`false_trigger ≈ 0.081`, the three detected agents) come from the **legacy
templated demo source** (`make_fixture.py`) and describe *mechanics*, not
recovery on realistic usage. Three measurement runs since have found:

1. **v1 detection only clustered because the fixtures were templated.** On
   realistic, varied phrasing the bag-of-tokens embedder (cosine 0.6) shatters
   every intent into near-singletons; holdout discovery falls to **0**.
2. **A real embedding model helps but is not a drop-in.** At the old 0.6
   threshold it over-merges into 2 clusters and `false_trigger` jumps
   0.061 → 0.632; recalibrated to **0.775** (scoped to `embedder_id`) it beats
   v1 — but GDG recovery still tops out at **2/7** planted intents, and of the
   candidates it births only a minority are clean (`docs/METRICS.md`, R10).
3. **It breaks contradiction detection.** Cosine measures topical relatedness,
   not contradiction, so the stability classifier detects nothing in a real
   embedding space and now returns `unavailable` — a disclosed gap surfaced at
   the human gate, never a reassuring "stable".

`docs/METRICS.md` is organised into three eras (A legacy demo / B realistic data
/ C real embedder = current) with per-number provenance; read the era labels.

## Status

P1–P3 of the v1 blueprint are implemented: two-hash store, three-stage build with
replay validation, the minimal detector, the container runtime with switch-cost
logging, the seven-state lifecycle with a shadow engine, the topology writer, and
the re-validator — plus a live Gemini substrate and the FastAPI dashboard. What
those mechanisms *recover on realistic data* is the subject of *Measured
findings* above and `docs/METRICS.md`.

Known limits, stated plainly: replay validates the **trigger only**, never answer
quality, and never the temporal period (`period_tested` is always false);
silence-based demotion is a shadow rule whose data the runtime does not yet
track; the lifecycle engine runs in **shadow mode** (humans move tags). See
`docs/METRICS.md` for what each number does and does **not** prove,
`docs/CAPABILITIES.md` for the capability-to-test map, and `docs/BLUEPRINT.md`
for the governing contract.
