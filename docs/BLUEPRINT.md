# CLE Implementation Blueprint v2 — Structure Before Code

Amends v1 with seven motivated changes (detection in v1 scope, replay
validation, three-stage evidence, anti-mimetism rule, APU lineage, TriggerSpec
resolution, three phases). This document is the contract for the v1 build.

## 0. Governance rule

Every component below cites the CLE need that justifies it. A component
justified only by "Docker has it" is rejected. (Motif: the CLE is the system;
Docker, Git, and the APU are vocabularies and lineages it draws from.)

## 1. Scope of v1

**In — both pillars, vertical slices:**
- Minimal detector: intent clustering (embedding of episode opener,
  incremental) + recurrence/reformulation counting per cluster, per-user
  baselines. No BOCPD (that's a v2 refinement of segmentation, not the
  introduction of detection).
- Three-stage build with replay validation (see §3).
- Two-hash Merkle store extension.
- Runtime: image/container split, mounts, Goodhart-bounded metrics volume.
- Lifecycle: tags (mobile states + immutable versions), engine in shadow mode,
  `topology.yaml` writer, re-validator.
- CLI: `cle build|run|ps|tag|log|diff`.

**Out (stub interfaces only):** BOCPD segmentation, auto-approval of
all-pinned candidates, registry, cross-host runtime spec.

## 2. Repo layout

```
cle/
  store/        # objects.py (content_hash, Block), commits.py (SourceSpec,
                # Image, tag refs), backends.py (Protocol, InMemory, Weaviate)
  detect/       # episodes.py (segmentation: silence + explicit markers for v1)
                # clusters.py (incremental intent clustering, per-user baseline)
                # signals.py (reformulation vs recurrence classification)
  build/        # resolver.py, replay.py (validation stage), assembler.py
  runtime/      # container.py, mounts.py, metrics_volume.py
  lifecycle/    # tags.py, engine.py (shadow mode), topology.py, revalidator.py
  cli/          # main.py (typer)
tests/          # property/ + unit/, hypothesis for invariants
```

## 3. The build — three stages, replay as validation

Need: agents born from usage have no a-priori eval suite; their own history is
the suite. (APU lineage: this generalizes the Living DLL's block auto-detection
— observe, propose, confirm — from memory blocks to whole agents.)

1. **Resolve** — every `#ref` exists in the store. Missing ref fails the build
   in ms; nothing consumed.
2. **Replay-validate** — replay the prompt history (window: `--replay-window`,
   default 30d) against the topology augmented with the candidate. Outputs:
   - `capture_rate`: fraction of the cluster's episodes the candidate's
     trigger would have intercepted;
   - `false_trigger_rate`: legitimate A/B/C traffic the candidate would have
     stolen (measured by replaying out-of-cluster episodes too);
   - `historical_cost`: mean iteration cost of the cluster under the current
     topology (the numeric justification of the birth).
   Replay validates the TRIGGER only — outputs are tagged `pre_evidence`.
   Answer quality is not and cannot be replay-tested (yesterday's user cannot
   rate an alternative answer).
3. **Assemble** — compile the system prompt in declared order, capture
   `model_fingerprint` (API version if exposed; else output hash over a fixed
   probe set), hash the complete artifact → Image.

## 4. Data model (deltas from v1 blueprint)

```python
class TriggerSpec(BaseModel, frozen=True):
    centroid: tuple[float, ...]      # produced by detect/, tested by replay
    period: PeriodSpec | None        # temporal condition for recurrence agents

class Image(BaseModel, frozen=True):
    source_hash: str
    resolved_refs: dict[str, str]
    assembled_prompt: str
    trigger: TriggerSpec             # ENTRYPOINT — immutable, in-image
    model_fingerprint: str           # need: substrate drift (see §6)
    pre_evidence: ReplayReport       # capture/false-trigger/historical cost
    hash: str
```

Invariants: see CLAUDE.md — two hashes, tag targets, Goodhart boundary,
staged builds consume nothing.

## 5. Evidence — three stages, enforced by types

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

## 6. Lifecycle engine — shadow mode in v1

Humans move tags via `cle tag`; the engine runs the part-7 state machine
thresholds (config, defaults from the article) in shadow and logs what it
would have done. The human/engine divergence log is article-9 material and the
calibration set for turning the engine live in v2.

## 7. topology.yaml

Written only by `lifecycle/topology.py`. Every change is a commit in the same
DAG under a `topology/` ref prefix (one store, one audit trail — decision 2 of
v1 blueprint, settled). Entries carry the evidence (or pre_evidence at birth)
that caused them. `cle log topology.yaml` renders the history with provenance,
approvals, and numbers; `cle diff` renders the learned-topology delta.

## 8. Test floor

- Property: build determinism (same source + same resolved components + same
  fingerprint ⇒ same image hash); two-hash inequality; staged-failure
  writes-nothing; replay window boundaries.
- Tamper: corrupt a stored component → resolve fails, integrity log fires.
- Goodhart: reflection test asserting Container exposes no metrics read path.
- Replay honesty: type-level test that PreEvidence cannot flow where Evidence
  is required.
- All tests on InMemoryStore; Weaviate backend behind the same Protocol,
  integration-tested separately.

## 9. Open decisions (settle during P1, in order of blast radius)

1. Episode segmentation for v1 without BOCPD: silence threshold + explicit
   markers — silence duration default? Proposal: 2× the user's median
   inter-message gap, floor 30 min.
2. Embedding model for clustering: same model as the agents (consistency) or
   a small dedicated embedder (cost)? Proposal: dedicated embedder; centroids
   must be stable across agent-model swaps or triggers break for free.
3. Probe set size for model_fingerprint: proposal 12 probes, drawn from the
   cluster's replay window at build time, frozen into the image.
