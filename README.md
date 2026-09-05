# Context Lifecycle Engine (CLE)

> A system that lets useful agents **emerge from how you actually work**, then
> earns or revokes their standing on lived evidence, never on prediction.

Reference implementation of the *Agent OS* series (parts 7 and 8). The CLE
watches a user's prompt history, detects recurring intents that deserve their own
agent, compiles each candidate into a content-addressed **image**, validates it
by replaying the user's own past, and moves it up and down a lifecycle ladder as
evidence accumulates or expires.

It borrows vocabulary from Docker (build / image / container / volumes /
topology), Git (a Merkle store) and the APU series (block auto-detection,
promoted to whole agents), but every component justifies itself by a CLE need,
not by the analogy. `docs/BLUEPRINT.md` is the contract.

---

## What it does, measured

Nine figures, each with its pinning key and reproduction command in
`docs/FINDINGS.md`. Read them together: several are one fact seen from two ends,
and publishing one without the other publishes half a measurement.

| what | figure |
|---|---|
| intents grouped, against Stack Overflow moderator ground truth | **32 / 48 = 67%**, against ~2% at random |
| the same run's cost | **`false_trigger_rate` 0.580**, `capture_rate` 1.000 |
| WildChat users with enough usage (≥40 turns, ≥30 days) | **0.34%** |
| of those, discarded by the coarse-timestamp guard | **29 of 40**, leaving ~0.08% of the corpus |
| occurrences of one intent for a first cluster | **~6**; **~10** for reliable recovery |
| episode count as a predictor | **nothing**. Occurrences per intent is the quantity |
| similarity floor, raw text / facets | **0.464** / **0.519 to 0.561** |
| dedicated vector storage | **not justified**: exhaustive search under 3 s at 1M vectors |
| cost of the facet boundary | **12.0 points** strict, **2.9** relaxed, centroid upper bound **99.3%** |

Two readings that matter more than any single number:

**The engine addresses intensive users, and that is the design.** 0.08% sounds
like failure until you notice what the other 99.92% have in common: they have not
repeated anything. The CLE refuses to manufacture an agent for them. Being unable
to serve a user who has no recurring intent is the feature.

**The signal lives in the tail, never in the mean.** Cohesion inside a 90 day
window against pairs a year apart: factor **1.08 on the mean**, factor **12.9 on
the share above cosine 0.7**. Any population level aggregator must therefore be a
tail mechanism; one reading means would see ~0.55 everywhere and conclude nothing.

### Two spaces, and they are not the same model

The engine embeds on `gemini-embedding-2`, through AI Studio by API key or
through Vertex at location `global` by application-default credentials: the same
space either way, cosine 1.000000. It is **deterministic for embedding**, so re
embedding the same 200 texts reproduces the committed cache exactly; the
generation model at T=0 is not, which is why every facet figure names its frozen
generation. The corpus benches run on BigQuery, which cannot host
`gemini-embedding-2`, so they run `gemini-embedding-001`. **Cosine between the
two spaces on the same texts is 0.040084**, so every bench figure is conditioned
on `gemini-embedding-001` and says so.

Numbers measured on fixtures rather than real corpora are in `docs/METRICS.md`.

---

## The contract, six invariants

Enforced in code, pinned by property tests.

1. **Two hashes.** A candidate's `SourceSpec.hash` is never its built
   `Image.hash`. Lifecycle tags attach to image hashes only.
2. **Goodhart boundary.** A `Container` exposes no read path to its own metrics.
   Metrics are written one way to a system-owned volume.
3. **Staged builds consume nothing.** A failed resolve, replay or assemble leaves
   the store byte identical.
4. **Every operation logs one JSON line**, with a mandatory `evidence` field on
   any upward tag move. No log, no merge.
5. **Replay proves the trigger, never the answer.** Replay outputs are
   `PreEvidence` and can never flow into a promotion.
6. **Proof expires.** Images freeze a `model_fingerprint`; the re-validator
   demotes an agent when the served model drifts.

A seventh, added after measurement: **a non-measurement is never a verdict.** A
check that cannot run in the configured vector space reports `unavailable`, and
the gap is disclosed rather than passing silently.

---

## Install

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"                 # engine + test suite
uv pip install -e ".[dev,dashboard]"       # + the FastAPI dashboard
uv pip install -e ".[dev,measure]"         # + the corpus measurement scripts
```

`cle dashboard` imports uvicorn; the reproduction commands in
`docs/FINDINGS.md` need pandas and the BigQuery client (`docs/BIGQUERY.md`).

## Configuration

```bash
cp .env.example .env   # then fill in GEMINI_API_KEY
```

`cle build`, `cle run` and `cle revalidate` call the LLM configured in `.env` on
their **live path**, the local default. **No key is required to run the tests**:
the suite uses stub fingerprinters and a committed vector cache. Pin a command's
substrate with `--model-id` (`current`, a model name, or `stub-*`).

`.env` is gitignored. Fingerprint probes run at temperature 0, so a fingerprint
delta means the model drifted, not that the sampler rolled differently.

---

## Quick start

```bash
# 1. Generate the LEGACY TEMPLATED demo history. The DETECTOR writes one agent
#    yaml per pattern, plus a hand-authored status_report incumbent.
uv run python examples/make_fixture.py

# 2. Three-stage build. capture_rate is measured against the CURRENT topology,
#    so build status_report first and weekly_recap drops to 0.60: the incumbent
#    already owns two of its episodes.
uv run cle build examples/weekly_recap_agent.yaml \
  --replay-window 40d --history examples/prompt_history_adversarial.jsonl

# 3. Instantiate in two workspaces and solicit.
uv run cle run weekly_recap --workspace alpha --prompts 2
uv run cle run weekly_recap --workspace beta  --prompts 4

# 4. Divergent per-container metrics, read across the Goodhart boundary.
uv run cle ps

# 5. Promote on lived evidence; the shadow engine judges the same evidence.
uv run cle tag weekly_recap trial
uv run cle tag weekly_recap ephemeral \
  --cost-ratio 0.6 --occurrences 4 --closures success,success,success,success

# 6. Topology history and the learned-topology delta.
uv run cle log topology.yaml
uv run cle diff topology/v1 topology/v3

# 7. Revalidate under a drifted model: proof expires, the agent auto-demotes.
uv run cle revalidate weekly_recap --model-id drifted-model-2
```

### The whole loop in one script

```bash
./examples/full_loop.sh
CLE_STORE=sqlite ./examples/full_loop.sh
CLE_MODEL_A=stub-model-a CLE_MODEL_B=stub-model-b ./examples/full_loop.sh
```

Twelve steps, on **real models by default**; the third form is the offline
deterministic run CI uses. Isolate any of them with `CLE_DEMO_STATE=/tmp/scratch`
so they never touch `.cle`. All era A figures: the source is templated.

### Live dashboard

```bash
uv run cle dashboard --state-dir .cle-demo --port 8000   # http://localhost:8000
```

Start on a scratch state. **"2. Run test" runs `full_loop.sh`, which deletes and
rebuilds the state directory it is given**, so it refuses `.cle` and greys the
button out rather than letting you find that out by pressing it. Drop
`--state-dir` to watch your own live state and forgo that button; add
`--store sqlite` if the CLI wrote sqlite.

One page (HTML + Alpine, no build step) served by FastAPI. Four zones: **Pulse**
(live oplog over SSE), **Births** (candidate cards with the Approve/Decline gate
and the disclosed-gap marker), **Lives**, **Topology**. The only write path is
Approve/Decline, routed through the CLI and logged as `human:dashboard`. See
`dashboard/README.md`.

---

## CLI reference

State lives in a directory (`--state-dir`, default `.cle/`). **`--state-dir` is
per command and goes AFTER the subcommand; `$CLE_STATE_DIR` is read by the
dashboard, never by the CLI.** `--store {file,sqlite}` is global and goes
**before** it:

```bash
uv run cle --store sqlite build ...      # not: cle build --store sqlite
```

The backends hold different paths (`.cle/store/` vs `.cle/store.db`), so
switching starts an empty store rather than half reading the other. The dashboard
sees what the CLI wrote only if launched with the same setting.

| Command | What it does |
|---|---|
| `cle build <src.yaml>` | Resolve, replay-validate, assemble; births the candidate. Replays against the current topology, so incumbents compete. `--replay-window`, `--history`, `--components`, `--model-id`. |
| `cle run <agent> --workspace <ws>` | Instantiate or switch the workspace's container and solicit it. `--prompts N`. |
| `cle ps` | Containers and their per-container metrics. |
| `cle tag <agent> <state>` | Move a state tag (`--cost-ratio`, `--occurrences`, `--closures`, `--reason`, `--note`). |
| `cle log [topology.yaml]` | Op-log tail, or topology history with provenance. |
| `cle diff <vA> <vB>` | Learned-topology delta between two versions. |
| `cle revalidate <agent>` | Replay the frozen probe set; on drift, auto-demote to `trial`. |
| `cle decline <agent>` | Refuse a candidate. Logs the refusal, moves no tag. |
| `cle dashboard` | Launch the FastAPI dashboard. `--port`. |
| `cle clean` | Reset the state directory. **Confirms first**; `--yes` to skip. |

`--model-id` defaults to `current`: the **live, billed** model.

---

## Architecture

**Two pillars.** *Detection*: episodes segmented on silence and explicit markers,
openers embedded and clustered, signals counted against a **per-user baseline**; a
cold user (<14 days, <20 episodes) gets no candidates. *Lifecycle*: candidates are
built, trialed, promoted, demoted, archived, resurrected, re-validated.

**Three-stage build.** *Resolve*: every `#ref` exists and re-hashes to its
address, or the build fails in milliseconds having written nothing.
*Replay-validate*: re-segment the window, route it against the topology plus the
candidate, report `capture_rate`, `false_trigger_rate` and `historical_cost` as
`PreEvidence`. *Assemble*: compile in declared order, freeze the probe set and
`model_fingerprint`, hash into an `Image`.

**The embedder is a substrate.** Three implementations behind one Protocol:
`RealEmbedder` (live, the only one needing a key), `CachedEmbedder` over committed
vectors (the suite default, a miss is an error), `StubEmbedder`. `TriggerSpec`
records `embedder_id` and `Image.hash` covers the trigger, so two images built on
different embedders have different hashes, and cross-space comparison raises. The
threshold travels with `embedder_id`: 0.6 for the stub, 0.775 for the real
embedder. One number cannot serve both.

**Ladder, five states in v1.** `archived(0) <-> candidate(1) <-> trial(2) <->
ephemeral(3) <-> pinned(4)`. `ephemeral` is promoted on lived `Evidence`;
`pinned` needs stability over ≥10 solicitations at non-worsening cost. The
**shadow engine** runs the part 7 thresholds and logs what it would do without
ever writing a ref.

> **Known divergence.** The published theory names **seven** states; v1
> implements **five**. Not reconciled, recorded rather than papered over.

**Three standards of proof.** `PreEvidence` (replay), `Evidence` (lived) and
`Persistence` (drift) are distinct types, so a function wanting `Evidence`
rejects the other two at type level. **Store**: content-addressed behind a
Protocol (`InMemoryStore`, `FileStore` default, `SqliteStore`), selected through
one `open_store` factory, all local. `topology.yaml` is written only by
`lifecycle/topology.py`, and a property test enforces that.

---

## Repository layout

```
cle/
  store/        objects, commits (SourceSpec, Image, TriggerSpec, evidence), backends
  detect/       episodes, clusters, embedders (+ provenance), signals, stability
  build/        resolver, replay, assembler, fingerprinter
  runtime/      container, mounts, metrics_volume
  lifecycle/    tags, engine (shadow), topology, revalidator, reasons (closed vocabulary)
  batch_guard.py  the three silent-failure guards
  cli/main.py   typer
dashboard/      backend/ (FastAPI + SSE), frontend/ (HTML + Alpine)
examples/       fixture generators, full_loop.sh, the committed vector cache
examples/bigquery/  the corpus measurement scripts (see its README)
docs/           BLUEPRINT (contract), FINDINGS (real corpora), METRICS (fixtures),
                CAPABILITIES (components), TESTING (tests), BIGQUERY (setup)
tests/          property/ + unit/, hypothesis for the invariants
```

## Testing

```bash
python -m pytest -q
```

**417 tests across 44 files**, fully offline. Five more run only where the private WildChat corpus is present, so they are not counted here: a suite size a reader cannot reproduce is not a suite size. A green suite pins the
**contract**, not the production vector space: 161 assertions are embedder
agnostic and hold in any era, while 31 pin the v1 stub mechanism only and do not
describe the production system. Details in `docs/TESTING.md`.

---

## Status

P1 to P3 of the v1 blueprint are implemented: two-hash store, three-stage build
with replay validation, the minimal detector, the container runtime with switch
cost logging, the five-state lifecycle with a shadow engine, the topology writer,
the re-validator, a live Gemini substrate, a real embedding substrate, and the
dashboard. Known limits, stated plainly:

* Replay validates the **trigger only**, never answer quality, never the period.
* Silence-based demotion is a shadow rule whose data the runtime does not track,
  and the lifecycle engine runs in **shadow mode**: humans move tags.
* **Contradiction detection needs an operator that is not a distance** and is
  inert until it gets one; the demo fixture source is **still templated**.
* `false_trigger_rate` 0.580 on the Stack Overflow corpus is a measured defect
  left frozen, not a target that was met, and the facet path is a **pilot**
  integrated into nothing.
