# CLE Implementation Blueprint v2, Structure Before Code

Amends v1 with seven motivated changes (detection in v1 scope, replay
validation, three-stage evidence, anti-mimetism rule, APU lineage, TriggerSpec
resolution, three phases). **This document is the contract for the v1 build.**

It states what the system must *be*. What it was measured to *do* on realistic
data is `docs/METRICS.md`: deliberately a separate document, because a
contract that quietly rewrites itself to match its results is not a contract.
Where measurement invalidated a design assumption, the assumption is marked
**SETTLED / REVISED** here with a pointer, and the reason is kept.

## 0. Governance rule

Every component below cites the CLE need that justifies it. A component
justified only by "Docker has it" is rejected. (Motif: the CLE is the system;
Docker, Git, and the APU are vocabularies and lineages it draws from.)

## 1. Scope of v1

**In, both pillars, vertical slices:**
- Minimal detector: intent clustering (embedding of episode opener,
  incremental) + recurrence/reformulation counting per cluster, per-user
  baselines. No BOCPD (that's a v2 refinement of segmentation, not the
  introduction of detection).
- Three-stage build with replay validation (see §3).
- Two-hash Merkle store extension.
- Runtime: image/container split, mounts, Goodhart-bounded metrics volume.
- Lifecycle: tags (mobile states + immutable versions), engine in shadow mode,
  `topology.yaml` writer, re-validator.
- CLI: `cle build|run|ps|tag|log|diff` (shipped also: `revalidate`, `decline`,
  `dashboard`, `clean`).

**Out (stub interfaces only):** BOCPD segmentation, auto-approval of
all-pinned candidates, registry, cross-host runtime spec.

## 2. Repo layout

```
cle/
  store/        # objects.py (content_hash, Block), commits.py (SourceSpec,
                # Image, TriggerSpec, evidence types), backends.py
                # (Protocol, InMemory, File, Sqlite, all local)
  detect/       # episodes.py (segmentation: silence + explicit markers for v1)
                # clusters.py (incremental intent clustering, per-user baseline)
                # embedders.py (Embedder impls + provenance + vector cache)
                # signals.py (reformulation vs recurrence classification)
                # stability.py (intra-cluster divergence classification)
  build/        # resolver.py, replay.py (validation stage), assembler.py
  runtime/      # container.py, mounts.py, metrics_volume.py
  lifecycle/    # tags.py, engine.py (shadow mode), topology.py, revalidator.py
                # reasons.py (the closed vocabulary, see 7b)
  batch_guard.py# guards against calls that return without working (see 8)
  cli/          # main.py (typer)
tests/          # property/ + unit/, hypothesis for invariants
```

## 3. The build, three stages, replay as validation

Need: agents born from usage have no a-priori eval suite; their own history is
the suite. (APU lineage: this generalizes the Living DLL's block auto-detection
- observe, propose, confirm, from memory blocks to whole agents.)

1. **Resolve**: every `#ref` exists in the store. Missing ref fails the build
   in ms; nothing consumed. Extended: declared tools must resolve and be of
   kind `tool`, and a trigger's required capability must be mounted.
2. **Replay-validate**: replay the prompt history (window: `--replay-window`,
   default 30d) against the topology augmented with the candidate. Outputs:
   - `capture_rate`: fraction of the cluster's episodes the candidate's
     trigger would have intercepted;
   - `false_trigger_rate`: legitimate A/B/C traffic the candidate would have
     stolen (measured by replaying out-of-cluster episodes too);
   - `historical_cost`: mean iteration cost of the cluster under the current
     topology (the numeric justification of the birth).
   Replay validates the TRIGGER only, outputs are tagged `pre_evidence`.
   Answer quality is not and cannot be replay-tested (yesterday's user cannot
   rate an alternative answer).
3. **Assemble**: compile the system prompt in declared order, capture
   `model_fingerprint` (API version if exposed; else output hash over a fixed
   probe set), hash the complete artifact → Image.

## 4. Data model (deltas from v1 blueprint)

```python
class TriggerSpec(BaseModel, frozen=True):
    centroid: tuple[float, ...]      # produced by detect/, tested by replay
    embedder_id: str                 # provenance: provider:model:dim, REQUIRED
    period: PeriodSpec | None        # temporal condition for recurrence agents

class Image(BaseModel, frozen=True):
    source_hash: str
    resolved_refs: dict[str, str]
    assembled_prompt: str
    trigger: TriggerSpec             # ENTRYPOINT, immutable, in-image
    model_fingerprint: str           # need: substrate drift (see §6)
    pre_evidence: ReplayReport       # capture/false-trigger/historical cost
    mounted_tools: tuple[str, ...]   # declared capabilities, hash-covered
    hash: str
```

**`embedder_id`: need (added after measurement).** A centroid is only
meaningful inside the vector space that produced it. An embedder swap
invalidates centroids exactly as a model swap invalidates a
`model_fingerprint`: one layer deeper, and this one touches agent
**identity**, because the trigger is what the agent *is*. Since `Image.hash`
covers the trigger, two images built on different embedders necessarily have
different hashes; comparing centroids across provenance raises
`SpaceMismatchError`, enforced where routing actually compares (candidate vs
each incumbent).

There is deliberately **no `model_version`**: the embedding API exposes no
version signal distinct from the model id, and storing a placeholder would give
false assurance about detecting silent provider-side drift.

Invariants (this document is their home): two hashes and tag targets (§4
above), the Goodhart boundary (§1 runtime scope), staged builds consume
nothing (§3.1), evidence type separation (§5), a non-measurement is never a
verdict (§5b), proof expires (§5). CLAUDE.md used to repeat this list.

## 5. Evidence, three stages, enforced by types

Need: cold-start (no a-priori evals), lived value, and substrate drift each
require a different standard of proof.

- **Replay → `pre_evidence`** (retrospective, zero risk): gates the build.
- **Trial → `evidence`** (lived, on natural occurrences): gates promotion.
  Mandatory field on every upward tag move.
- **Monitoring → `persistence`**: the re-validator replays the image's probe
  set when the served model changes (or on schedule when versions aren't
  exposed). Fingerprint drift → auto-demote to trial, log
  `{"op":"revalidation_failed", ...}`. Proof has an expiration date.

Three distinct Pydantic types; a function expecting `Evidence` rejects
`PreEvidence` at type level.

### 5b. A non-measurement is not a verdict

Need (added after measurement): the detector runs checks whose *soundness*
depends on the substrate. When such a check cannot run, the system must say so
rather than return a reassuring pass. Two mechanisms enforce this:

- **Three-valued stability verdict**: `stable` / `unstable` / **`unavailable`**.
  The contradiction check reports `unavailable` in any vector space its
  heuristic is not calibrated for.
- **Veto, not precondition**: an `unstable` cluster yields no candidate
  ("don't automate a self-contradicting pattern"). But `unavailable` does
  **not** block birth: the candidate is born carrying `stability="unavailable"`
  in its provenance, surfaced to the human at the override gate. Blocking on a
  check's *absence* would give it weight it never had and would stop the first
  pillar producing anything at all; a system that detects nothing is worse than
  one that proposes with a documented gap. The gap is disclosed, never silent.

Same principle as `PreEvidence != Evidence`, and as the `degenerate` resolution
diagnostic: a weak or absent measurement must never masquerade as a strong one.

## 6. Lifecycle engine, shadow mode in v1

Humans move tags via `cle tag`; the engine runs the part-7 state machine
thresholds (config, defaults from the article) in shadow and logs what it
would have done. The human/engine divergence log is article-9 material and the
calibration set for turning the engine live in v2.

## 7. topology.yaml

Written only by `lifecycle/topology.py`. Every change is a commit in the same
DAG under a `topology/` ref prefix (one store, one audit trail, decision 2 of
v1 blueprint, settled). Entries carry the evidence (or pre_evidence at birth)
that caused them. `cle log topology.yaml` renders the history with provenance,
approvals, and numbers; `cle diff` renders the learned-topology delta.

The record also carries **`embedding`**, at TOPOLOGY scope and never per agent:
the `embedder_id`, the cluster threshold, and where that threshold came from. It
is supplied at the first write and inherited afterwards, and a later write that
declares a different space is refused rather than allowed to inherit silently.

This is an AGGREGATION KEY, not metadata. Two instances running the same
embedder at different thresholds do not birth the same agents from the same
usage, so a topology history without this field is comparable to nothing, and a
population report that aggregated it anyway would measure its own
instrumentation. Any reader of the history, the dashboard included, must be able
to see it.

### 7b. The boundary free text does not cross

`topology.yaml` is the only file a future population level reads. Two fields
could carry a descent's motive across it, and they are separated by TYPE, not
by a write-time filter, a filter is bypassed by the next path someone adds:

| field | where it lives | who reads it | shape |
|---|---|---|---|
| `reason` | `topology.yaml` **and** the oplog | user + population level | closed vocabulary (`cle/lifecycle/reasons.py`) |
| `note` | the oplog only | the user, locally | free text |

The vocabulary is split on two axes, deliberately not merged into one field:
**engine-authored** (`substrate_drift`, `silence`: a metric
fired) versus **human-authored** (`cost_regression`: somebody judged); and
**descent** versus **decline** (a decline says the detection was right and the
moment was not, counting it as a rejection would be a product contresens).
`engine_disagrees` is human but stays isolable, so an aggregate claiming to
measure independent human judgement can exclude the engine's own influence.

Out-of-vocabulary values raise (`UnknownReasonError`); there is no `other`
bucket, which would silently absorb the distinction the field exists to make.
`cluster_stability`'s `reason=` is a technical diagnostic on a technical op and
is explicitly exempt, a coincidence of keyword, not a shared meaning.

### 7c. Population minimum, decided, and insufficient

An aggregate over a population must not become a way to read one person's
usage. The decision taken: **a single global floor**: below it, the agent NAME
is suppressed from any population output.

Two properties of that decision are recorded here rather than softened:

- **Suppression, not a warning.** A warning leaves the name on screen and asks
  the reader to disregard it, which is not a protection.
- **A single global floor is insufficient, and is known to be.** A rare agent
  name can identify a team long before any global count is reached, and one
  floor cannot express that. It is what this codebase implements; it is not
  what the problem requires. No population output exists yet, so nothing
  currently depends on it, the gap is stated now so it is not discovered as a
  surprise by whoever builds level 2.

## 8. Test floor

- Property: build determinism (same source + same resolved components + same
  fingerprint ⇒ same image hash); two-hash inequality; staged-failure
  writes-nothing; replay window boundaries.
- Tamper: corrupt a stored component → resolve fails, integrity log fires.
- Goodhart: reflection test asserting Container exposes no metrics read path.
- Replay honesty: type-level test that PreEvidence cannot flow where Evidence
  is required.
- All invariant tests on InMemoryStore; File and Sqlite backends share the
  Protocol and its conformance suite. There is no remote backend.
- **Offline by construction**: no test may require a key or the network. The
  detection embedder in tests is a committed vector cache; a cache miss is an
  error, never a live call, and a test asserts no test module imports the live
  embedder.
- **Scope honesty**: every test module states the vector space its assertions
  hold in. A test whose claim is true only in the stub space must say so and
  must not read as a general invariant (see `docs/CAPABILITIES.md`, the
  three-bucket classification).
- **A guard counts only if removing it turns the suite red.** An exception class
  named in a test file says nothing about which of its raise sites is covered.
  `python tools/mutate.py` decides that by experiment, per site, and its own
  correctness is itself tested.
- **The suite owns its environment.** `$CLE_STORE`, `$CLE_EMBEDDER`,
  `$CLE_VECTOR_CACHE` and `$CLE_FORCE_REAL_MODEL` select backends and substrates
  at call time, and `.env` is re-read by any module that loads it, so a test
  session inherits the operator's shell unless it refuses to. It refuses: the
  variables are cleared and `load_dotenv` is neutralised for the session.
  Without that the suite is green on one machine and red on another, for a
  reason no test names.

## 9. Open decisions, status after P1

1. **SETTLED.** Episode segmentation without BOCPD: silence threshold +
   explicit markers, silence = 2× the user's median inter-message gap, floor
   30 min. Shipped as proposed.

2. **SETTLED, then REVISED by measurement.** Embedding model for clustering:
   a dedicated embedder, not the agents' model, confirmed, and for the stated
   reason (centroids must survive agent-model swaps). Measurement then added
   three things the proposal did not anticipate:
   - the embedder is a **substrate with provenance**, so `TriggerSpec` records
     `embedder_id` and cross-space comparison raises (§4);
   - the **clustering threshold is a property of the vector space**, not a
     global constant: bag-of-tokens puts same-domain text at ~0.2–0.4, a real
     sentence embedder at ~0.7–0.9. One number cannot serve both, so the
     threshold travels with `embedder_id` (0.6 for `stub:hashed64`, 0.775 for
     `google:gemini-embedding-2:768`);
   - **cosine is the wrong operator for contradiction.** It measures topical
     relatedness; opposing directives score 0.62–0.86 *because they are about
     the same thing*. The four-type contradiction taxonomy is therefore inert
     in a semantic space, which is why §5b exists. A signed/entailment operator
     is required and is **not** in v1 scope.
   Numbers: `docs/METRICS.md` (embedder upgrade run).

3. **SETTLED.** Probe set for `model_fingerprint`: 12 probes drawn from the
   cluster's replay window at build time, frozen into the image.

## 10. What this contract does not promise

Stated here so no reader infers it from the sections above:

- Replay proves a **trigger**, never answer quality, and never the temporal
  period (`period_tested` is always false in v1).
- A fingerprint delta proves the **substrate changed**, not that the agent got
  worse; a better model demotes exactly as a degraded one does.
- Detection **recovering** a user's real intents is a measured quantity, not a
  contractual guarantee. On realistic data v1 recovers a minority of planted
  intents (`docs/METRICS.md`); the mechanisms above are what the system *does*,
  not a claim about how well.
- The lifecycle engine is in **shadow mode**: humans move every tag.
