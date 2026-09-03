---
name: cle-core-contracts
description: Data models, hashing rules, log line format, and invariant tests for the CLE store, build, runtime, and lifecycle. Use when implementing or reviewing anything in cle/store, cle/build, cle/runtime, cle/lifecycle, or their tests.
---

# CLE Core Contracts

## Hashing
- One function: `content_hash(obj) -> str` — canonical JSON (sorted keys, no
  whitespace, UTF-8), sha256 hexdigest. Never inline hashlib elsewhere.
- Verify on read: every component fetched is re-hashed against the requested
  hash before use. Mismatch → integrity protocol: abort use, log
  `{"op":"integrity_violation",...}`, refetch from backend; never crash,
  never silently inject.

## Models (frozen unless stated)
- `SourceSpec(yaml_raw, hash)` — the candidate's source.
- `TriggerSpec(centroid, embedder_id, period)` — the ENTRYPOINT.
  `embedder_id` (`provider:model:dim`) is REQUIRED: a centroid is only
  meaningful inside the vector space that produced it, so an embedder swap
  invalidates centroids exactly as a model swap invalidates a fingerprint —
  one layer deeper, and this one touches agent IDENTITY. Cross-space
  comparison raises `SpaceMismatchError` (enforced in replay, where routing
  actually compares candidate vs incumbents). Deliberately NO `model_version`:
  the embedding API exposes no version signal distinct from the model id, and
  a placeholder would give false drift assurance.
- `Image(source_hash, resolved_refs, assembled_prompt, trigger,
  model_fingerprint, pre_evidence, probe_set, mounted_tools,
  probe_output_hashes, hash)` — built artifact. `hash` covers ALL fields.
  Tags attach here only. `mounted_tools` = declared capability names;
  `probe_output_hashes` lets the re-validator LOCALIZE drift.
- `Container(image_hash, workspace_id, mounts, metrics_volume_id)` — mutable
  record. MUST NOT expose any metrics read path (no method, property, or
  context injection). The runtime writes metrics through
  `metrics_volume.record(container_id, event)` — one-way.
- `PreEvidence(capture_rate, false_trigger_rate, historical_cost, window,
  semantic_trigger_tested, period_tested)` vs
  `Evidence(cost_ratio, occurrences, closure_tags)` vs
  `Persistence(fingerprint_at_build, fingerprint_now, probe_deltas)` —
  three distinct types. Functions gate on the exact type they need.

## A non-measurement is never a verdict
When a check's soundness depends on the substrate, it must say so rather than
return a reassuring pass:
- the stability verdict is THREE-valued: `stable` / `unstable` / `unavailable`;
- `unstable` VETOES a birth; `unavailable` does NOT — the candidate is born
  carrying `stability="unavailable"` in its provenance, disclosed to the human
  at the override gate. Blocking on a check's *absence* would give it weight it
  never had and would stop the first pillar producing anything at all.
Same principle as `PreEvidence != Evidence` and the `degenerate` resolution
diagnostic. Never record `stability="stable"` when the check did not run.

## Topology records: two closed contracts

`topology.yaml` is written by `cle/lifecycle/topology.py` and nothing else (a
property test enforces the single writer). Two fields are constrained by TYPE,
not by a write-time filter, because a filter is bypassed by the next path
someone adds:

- **`reason` is a closed vocabulary** (`cle/lifecycle/reasons.py`). Passing
  `cause["reason"]` raises `FreeTextInTopologyError`; the only route in is
  `reason=TopologyReason(...)` over a `Literal`. Two axes, deliberately not one
  field: ENGINE (`substrate_drift`, `silence`) vs HUMAN (`cost_regression`), and
  DESCENT vs DECLINE (`engine_disagrees`, `defer`). `engine_disagrees` must stay
  isolable: it is a human who deferred to the engine, and aggregating it as an
  independent judgement is the Goodhart constraint at population scale. Free
  user text belongs to the oplog note, which level 2 never reads.
  A member with no producer gets REMOVED, not kept as a slot: `repeated_harm`
  went in R36 because no rule emits it.
- **`embedding` is an aggregation key**, at TOPOLOGY scope, never per agent.
  `EmbeddingConfig(embedder_id, cluster_threshold, calibration)`, supplied at
  the first write and inherited afterwards. A write declaring a different space
  raises `EmbeddingConfigMismatchError`; a first write with none raises
  `MissingEmbeddingConfigError`. Two instances at different thresholds do not
  birth the same agents from the same usage, so a report aggregating topologies
  without grouping on this key measures its own instrumentation.

## Guards against silent failure (`cle/batch_guard.py`)

The recurring failure shape: something returns, and returning is not working.

- `assert_batch_varied` — a batch whose outputs are all identical, or whose
  error share exceeds 0.2, is a failed batch even though every call returned.
- `assert_unit_norm` — `cosine` is a raw dot product and is a cosine only on
  unit vectors. Refuses vectors from a surface that does not normalise.
- `assert_embeddable` — the only OUTBOUND guard: everything else on the
  embedding path checks what comes back, so an empty opener used to be billed
  and then clustered as if it named an intent.

## Log line format (one per operation, JSON, single line)
```json
{"op":"build|run|switch|tag|revalidate|topology_write|...",
 "ts":"iso8601","actor":"human:<id>|engine:shadow|engine:live|engine:revalidator|system:<component>",
 "image":"<hash8>","from":"<state?>","to":"<state?>",
 "evidence":{...}|"pre_evidence":{...}|"persistence":{...},
 "latency_ms":n}
```
Upward tag moves REQUIRE `evidence`. Builds carry `pre_evidence`.
Re-validations carry `persistence`. Ops outside that family carry `op/ts/actor`
plus their own context keys — currently `closure_distribution`,
`cluster_stability`, `integrity_violation`, `detector_observing`,
`candidate_declined`, `revalidation_failed`.
A PR adding an operation without its log line is rejected.

## Store
- Backend Protocol: `put(hash, bytes)`, `get(hash)`, `move_ref(name, hash)`,
  `list_refs(prefix)`. Implementations, all Protocol-conformant and all
  exercised by the default suite: `InMemoryStore` (the default, and the only
  one the invariant tests need), `FileStore` (persistent CLI/dashboard state),
  `SqliteStore` (persistent, inspectable, stdlib sqlite3).
  Both persistent backends are local and offline; there is no remote
  backend and no test depends on an external service.
- Refs: `agents/<name>/<state>` (mobile), `agents/<name>/v<semver>`
  (immutable — moving one raises), `topology/<version>`.
- Semver rule: major = trigger changed, minor = component ref swapped,
  patch = lifecycle thresholds only.
- Lifecycle states implemented in v1 (`STATE_RANK`): `archived`(0),
  `candidate`(1), `trial`(2), `ephemeral`(3), `pinned`(4) — **five**. The
  published part-7 machine names more (`pattern`, `deprecated`); those are NOT
  in the code. Do not reference them as if they were.

## Offline by construction
No test may need a key or the network. The detection embedder in tests is
`CachedEmbedder` over committed vectors: a cache miss is an ERROR, never a live
call. `RealEmbedder` is generation-only and must not be imported by any test
module (asserted). Fingerprinters are stubbed.

## Tests that must exist before the code they guard
1. `test_two_hash_inequality` — build never yields image.hash == source.hash.
2. `test_tag_source_raises` — TagTargetError on tagging a source hash.
3. `test_goodhart_boundary` — reflection: no attribute/method on Container
   returns metrics.
4. `test_staged_failure_writes_nothing` — failed resolve/replay leaves store
   byte-identical (snapshot compare).
5. `test_pre_evidence_not_evidence` — type-level: promotion API rejects
   PreEvidence.
6. `test_build_determinism` — hypothesis: same inputs ⇒ same image hash.
7. `test_embedder_swap_changes_the_image_hash` (+ cross-space comparison
   raises) — centroid provenance is part of agent identity.
8. `test_vector_cache_has_one_distinct_vector_per_text` — a silent batching
   collapse in the committed cache must fail the suite, not be eyeballed.
9. One test per RAISE SITE of every guard, not one per exception class. R36
   mutated each `raise` in turn and found three unenforced: `cosine`'s
   dimension check had no test at all, and two of the three
   `SpaceMismatchError` sites were free because the third looked covered. An
   exception class appearing in a test file proves nothing about the site you
   care about.
10. `$CLE_VECTOR_CACHE` is a PATH override, never a SPACE override. A cache
   declaring a foreign `embedder_id` must still be refused at the topology
   write, including when someone adds its calibration entry.

## Scope honesty in tests
Every test module states the vector space its assertions hold in. Three buckets
(counts in docs/TESTING.md): **embedder-agnostic** (the invariant core),
**stub-as-a-tool** (stub incidental, claim space-independent), and
**stub-as-the-subject** (true ONLY in `stub:hashed64`). A bucket-3 module must
carry a SCOPE header and must not read as a general invariant — property tests
especially, since their format claims generality by itself.
