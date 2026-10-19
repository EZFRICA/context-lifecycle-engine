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
