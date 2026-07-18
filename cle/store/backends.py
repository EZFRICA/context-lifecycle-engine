"""Storage backend Protocol and implementations.

Contract (cle-core-contracts):
- Protocol: `put(hash, bytes)`, `get(hash)`, `move_ref(name, hash)`,
  `list_refs(prefix)`.
- Refs: `agents/<name>/<state>` (mobile), `agents/<name>/v<semver>`
  (immutable — moving one raises), `topology/<version>`.
- `InMemoryStore` is the default and the only test dependency. WeaviateStore
  (client v4) mirrors the Protocol; integration-tested separately — no unit
  or property test may import it.

Implemented in commit 3 (feat(store): specs, refs, backends).
"""
