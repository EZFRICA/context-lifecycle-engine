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
- `Image(source_hash, resolved_refs, assembled_prompt, trigger,
  model_fingerprint, pre_evidence, hash)` — built artifact. `hash` covers ALL
  fields. Tags attach here only.
- `Container(image_hash, workspace_id, mounts, metrics_volume_id)` — mutable
  record. MUST NOT expose any metrics read path (no method, property, or
  context injection). The runtime writes metrics through
  `metrics_volume.record(container_id, event)` — one-way.
- `PreEvidence(capture_rate, false_trigger_rate, historical_cost, window)` vs
  `Evidence(cost_ratio, occurrences, closure_tags)` vs
  `Persistence(fingerprint_at_build, fingerprint_now, probe_deltas)` —
  three distinct types. Functions gate on the exact type they need.

## Log line format (one per operation, JSON, single line)
```json
{"op":"build|run|tag|revalidate|topology_write",
 "ts":"iso8601","actor":"human:<id>|engine:shadow|engine:live|engine:revalidator|system:<component>",
 "image":"<hash8>","from":"<state?>","to":"<state?>",
 "evidence":{...}|"pre_evidence":{...}|"persistence":{...},
 "latency_ms":n}
```
Upward tag moves REQUIRE `evidence`. Builds carry `pre_evidence`.
Re-validations carry `persistence`. A PR adding an operation without its log
line is rejected.

## Store
- Backend Protocol: `put(hash, bytes)`, `get(hash)`, `move_ref(name, hash)`,
  `list_refs(prefix)`. InMemoryStore is the default and the only test
  dependency. Weaviate (client v4) mirrors it; integration tests separate.
- Refs: `agents/<name>/<state>` (mobile), `agents/<name>/v<semver>`
  (immutable — moving one raises), `topology/<version>`.
- Semver rule: major = trigger changed, minor = component ref swapped,
  patch = lifecycle thresholds only.

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
