# CLE Implementation Blueprint v2, Structure Before Code

Amends v1 with seven motivated changes (detection in v1 scope, replay
validation, three-stage evidence, anti-mimetism rule, APU lineage, TriggerSpec
resolution, three phases). **This document is the contract for the v1 build.**

It states what the system must *be*. What it was measured to *do* on realistic
data is `docs/METRICS.md`, a separate document: a design intent and a
measurement answer different questions and are not interchangeable.

**Every document in this repo describes the code as it stands, not its own
history.** When the code moves, the document is rewritten to match; a section
that has been overtaken is replaced, never annotated with what it used to say.
Where measurement invalidated a design assumption, the assumption is marked
**SETTLED / REVISED** with the reason - that mark records *why the design is
what it is*, which is still a fact about the present code, not a changelog.
Change history belongs to git, and to `EVOLUTION.md`: gitignored, the one
document allowed to trace how the system got here, legacy included.


- [0. Governance rule](blueprint/governance-rule.md) - Every component below cites the CLE need that justifies it. A component
- [1. Scope of v1](blueprint/scope-of-v1.md) - incremental) + recurrence/reformulation counting per cluster, per-user
- [2. Repo layout](blueprint/repo-layout.md) - cle/
- [3. The build, three stages, replay as validation](blueprint/the-build-three-stages-replay-as-validation.md) - Need: agents born from usage have no a-priori eval suite; their own history is
- [4. Data model (deltas from v1 blueprint)](blueprint/data-model-deltas-from-v1-blueprint.md) - class TriggerSpec(BaseModel, frozen=True):
- [5. Evidence, three stages, enforced by types](blueprint/evidence-three-stages-enforced-by-types.md) - Need: cold-start (no a-priori evals), lived value, and substrate drift each
- [6. Lifecycle engine, shadow mode in v1](blueprint/lifecycle-engine-shadow-mode-in-v1.md) - Humans move tags via `cle tag`; the engine runs the part-7 state machine
- [7. topology.yaml](blueprint/topology-yaml.md) - Written only by `lifecycle/topology.py`. Every change is a commit in the same
- [8. Test floor](blueprint/test-floor.md) - fingerprint ⇒ same image hash); two-hash inequality; staged-failure
- [9. Open decisions, status after P1](blueprint/open-decisions-status-after-p1.md) - 1. **SETTLED.** Episode segmentation without BOCPD: silence threshold +
- [10. What this contract does not promise](blueprint/what-this-contract-does-not-promise.md) - Stated here so no reader infers it from the sections above:
