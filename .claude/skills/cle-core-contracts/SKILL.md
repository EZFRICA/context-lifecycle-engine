---
name: cle-core-contracts
description: Data models, hashing rules, log line format, and invariant tests for the CLE store, build, runtime, and lifecycle. Use when implementing or reviewing anything in cle/store, cle/build, cle/runtime, cle/lifecycle, or their tests.
when_to_use: Touching cle/store, cle/build, cle/runtime or cle/lifecycle; adding a model field, a ref, a log line or an op; asking what an invariant requires or which lifecycle states exist.
---

# CLE Core Contracts

The rules below hold in every change under `cle/`. The detail of each is one
file away; open the file when you are about to touch that area, not before.

## Always true, no file needed

- **One hashing function.** `content_hash(obj)` over canonical JSON, sha256.
  Never inline `hashlib` elsewhere, and verify on read: a component is re-hashed
  against the address it was fetched by, before use.
- **Two hashes.** A candidate's `SourceSpec.hash` is never its `Image.hash`.
  Tags attach to image hashes only.
- **Three evidence types.** `PreEvidence` (replay) / `Evidence` (lived) /
  `Persistence` (fingerprint) are distinct types and functions gate on the exact
  one they need. Replay output can never reach a promotion.
- **A non-measurement is never a verdict.** A check that could not run reports
  `unavailable`; it never reports a reassuring pass.
- **Five lifecycle states exist** (`archived`, `candidate`, `trial`,
  `ephemeral`, `pinned`). The published machine names more; the store cannot
  hold them, so nothing may render them as if it could.
- **One JSON line per operation**, and an upward tag move carries `evidence`.
  No log, no merge.
- **Addresses are 64 hex characters**, refused otherwise on `put` and `get`: an
  address becomes a filename, so it is an untrusted path component.
- **A guard ships with a test that goes red when the guard is removed**, per
  raise site - not one test per exception class.

## Open when you touch that area

| area | file |
|---|---|
| canonical hashing and the integrity protocol | [hashing.md](reference/hashing.md) |
| `SourceSpec`, `TriggerSpec`, `Image`, `Container`, the evidence types | [models-frozen-unless-stated.md](reference/models-frozen-unless-stated.md) |
| three-valued stability, and why `unavailable` does not veto | [a-non-measurement-is-never-a-verdict.md](reference/a-non-measurement-is-never-a-verdict.md) |
| the closed reason vocabulary and the embedding aggregation key | [topology-records-two-closed-contracts.md](reference/topology-records-two-closed-contracts.md) |
| the three silent-failure guards | [guards-against-silent-failure-cle-batch-guard.md](reference/guards-against-silent-failure-cle-batch-guard.md) |
| the oplog line's exact shape and its op family | [log-line-format-one-per-operation-json-single.md](reference/log-line-format-one-per-operation-json-single.md) |
| backends, refs, semver, `StagedStore`, address validation | [store.md](reference/store.md) |
| why no test may need a key or the network | [offline-by-construction.md](reference/offline-by-construction.md) |
| the property tests that must exist before the code | [tests-that-must-exist-before-the-code-they-gua.md](reference/tests-that-must-exist-before-the-code-they-gua.md) |
| the three test buckets and the SCOPE header | [scope-honesty-in-tests.md](reference/scope-honesty-in-tests.md) |
