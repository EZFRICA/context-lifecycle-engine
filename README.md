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
the suite uses stub fingerprinters and a committed vector cache. Pin a command's substrate with
`--model-id` (`current`, a model name, or `stub-*`).

`.env` is gitignored. Fingerprint probes run at temperature 0, so a delta means
the model drifted, not that the sampler rolled differently.

**Logs.** Diagnostics (a retry, a fallback, an error a run survives) go to stderr
through `cle/logs.py`; what a command reports stays on stdout, where scripts and
tests read it, and the oplog stays the audit record. Nothing below WARNING is
shown unless `CLE_LOG_LEVEL` asks for it (`DEBUG`, `INFO`, `WARNING`, `ERROR`),
and nothing is written to disk unless `CLE_LOG_FILE` names a file - that one
rotates at 5 MiB, keeping three previous files. A log line never carries user
text: a probe is logged by its position, a failure by its exception type.

Importing `cle` configures nothing. The entry points do it - the CLI callback,
the dashboard's startup, each script's `main()` - so embedding this package in
another application leaves that application's own logging exactly as it was.

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

**On other live models.** `CLE_MODEL_A` and `CLE_MODEL_B` take any model name.
Add `CLE_FORCE_REAL_MODEL=1`: without it, a name the provider does not serve
falls back silently, to an offline hash for the fingerprint and to
`generation_failed` for the facet.

```bash
CLE_FORCE_REAL_MODEL=1 CLE_MODEL_A=gemini-3.6-flash CLE_MODEL_B=gemini-3.8-flash \
  CLE_DEMO_STATE=/tmp/scratch ./examples/full_loop.sh
```

Measured 2026-09-10, one run per pair, both exit 0 on every step:

| | `gemini-3.5-flash-lite` → `gemini-3.6-flash` (default) | `gemini-3.6-flash` → `gemini-3.8-flash` |
|---|---|---|
| build: capture / false trigger / cost | 1.000, 0.600 / 0.081 / 3.40, 2.67, 7.00 | identical |
| revalidation under model B | `DRIFT: 5/5 probes moved` | `DRIFT: 5/5 probes moved` |
| v2 rebuilt on model B | distinct successor image | distinct successor image |
| facets written at birth | 4 of 4 `present`, 106 to 171 characters | 4 of 4 `present`, 84 to 119 characters |

What differs between the two pairs is the facet text, and only that:

- **Length and form.** `gemini-3.5-flash-lite` writes longer sentences in the
  imperative (*"Investigate and troubleshoot sudden performance degradation
  ..."*); `gemini-3.6-flash` writes shorter ones in the third person
  (*"Investigates performance degradation ..."*). Both satisfy the prompt's
  "start with a verb", and neither was refused.
- **Separation.** Under `gemini-3.6-flash` the `weekly_recap` and
  `status_report` facets come out as near paraphrases (*weekly project status
  summaries* / *weekly project status updates and recaps*). One run cannot say
  whether that is the model or its sampling.

What does not differ, and why:

- **The build figures** are identical because replay calls no model: it
  classifies recorded episodes in the embedder's space.
- **The revalidation row** is 5/5 on both pairs, but it does not separate them.
  A live model at temperature 0 also reports drift against itself
  (`cle/llm_provider.py`, `get_fingerprint_llm`).

### Live dashboard

```bash
uv run cle dashboard --state-dir .cle-demo --port 8000   # http://localhost:8000
```

Start on a scratch state. **"2. Run test" runs `full_loop.sh`, which deletes and
rebuilds the state directory it is given**, so it refuses `.cle` and greys the
button out. Drop `--state-dir` to watch your live state and forgo that button;
add `--store sqlite` if the CLI wrote sqlite.

One page (HTML + Alpine, no build step) served by FastAPI. Four zones: **Pulse**
(live oplog over SSE), **Births** (candidate cards with the Approve/Decline gate
and the disclosed-gap marker), **Lives**, **Topology**. Approve/Decline is the
audience-facing write path, routed through the CLI and logged as
`human:dashboard`; the operator controls (init, run test, clean, the demo) write
too, and a write sent from another site is refused. See `dashboard/README.md`.

### Level 2: the population layer

Level 2 is in the engine, in its own package, `cle/population/`. Every true
birth writes a **facet** - one sentence describing what the agent does - into
its topology entry, and `cle population` reads the topologies of many instances,
one per user, and groups their agents by what they do (Clio's four stages):

```bash
uv run cle population .cle-user-a .cle-user-b .cle-user-c --out .cle-population
```

It reads `topology.yaml` records and nothing else, and writes `report.json` and
one op line under `--out`. A group is named only when at least 3 members come
from at least 3 distinct users, and a name carrying a proper noun or a long
number is refused rather than shown; below the floor a group keeps its id and
its size and loses only its name. The report never quotes a facet. `--threshold`
is a parameter: the right value depends on the corpus. See
`docs/CAPABILITIES.md` §12.

**Live, on three models.** Three users born on a live model, then grouped by it:

```bash
CLE_FORCE_REAL_MODEL=1 uv run python examples/run_multiuser.py \
  --state-root /tmp/l2 --embedder cached --model-id gemini-3.8-flash
GEMINI_MODEL=gemini-3.8-flash uv run cle --embedder real population \
  /tmp/l2/user1 /tmp/l2/user2 /tmp/l2/user3 --namer live --out /tmp/l2-pop
```

Measured 2026-09-10, one run per model, in `google:gemini-embedding-2:768` at
its calibrated 0.775 (no `--threshold`, so the space's value applies):

| | `gemini-3.5-flash-lite` | `gemini-3.6-flash` | `gemini-3.8-flash` |
|---|---|---|---|
| facets written at birth | 3 of 3 `present` | 3 of 3 `present` | 3 of 3 `present` |
| groups (sizes) | 2 (2, 1) | 2 (2, 1) | 2 (2, 1) |
| the pair grouped | events + venue (0.884) | **events + newsletter** (0.787) | events + venue (0.810) |
| families at 0.735 | 2 | 2 | **1** |
| named | 0 | 0 | 0 |
| facets quoted in the report | 0 | 0 | 0 |

The sizes agree on all three models; the members do not. Under
`gemini-3.6-flash` the events facet reads closer to the newsletter one than to
the venue one, so the pair changes while every count stays the same: a report
of sizes alone cannot show a change of model. Under `gemini-3.8-flash` the
singleton joins the pair one level up. Nothing is named on any model, because
three users is the floor itself and no group reaches it. The runs exercise the
path, not a population, and one run per model cannot separate the model from its
sampling.

### Level 2 board

`open dashboard_level_2/index.html` - the same stages, run by the engine's code
over three bench corpora in BigQuery's vector space. Self-contained, no server,
no build step. Three sources behind one selector:

| source | real users | labels | what it can answer |
|---|---|---|---|
| Stack Overflow, cross-author | yes | yes, moderator duplicates | recall at a matched false-positive rate |
| WildChat, 40 users, 130 clusters | yes | no | what the layer actually sees |
| GDG, 12 synthetic users | no | yes, planted intents | purity and completeness, hence calibration |

It shows the two candidate architectures at parity - raw episodes against
generated facets - with what each buys and what it costs, and it does not pick
one: the ranking reverses with the error budget (`docs/FINDINGS.md` §6c), so the
choice belongs to whoever sets that budget.

The floor and the screen are the engine's: on WildChat no group reaches 3
distinct users, so the corpus names nothing at all. The numbers are in
`dashboard_level_2/README.md`.

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
| `cle decline <agent>` | Refuse what the system proposes for an agent (a birth, or a further promotion). Logs the refusal, moves no tag; `--reason` takes only `engine_disagrees` or `defer`. |
| `cle population <dir>...` | Level 2: group the agents of many instances by their facets. Reads each `topology.yaml` only, writes `report.json` under `--out`. `--threshold`, `--namer stub\|live`. |
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
  logs.py       diagnostics to stderr; level and file from the environment
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
uv run pytest -q
```

**555 tests across 54 files**, fully offline. Five more run only where the private WildChat corpus is present, so they are not counted here: a suite size a reader cannot reproduce is not a suite size. A green suite pins the
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
