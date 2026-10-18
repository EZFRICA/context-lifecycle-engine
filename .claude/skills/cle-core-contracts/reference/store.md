## Store
- Backend Protocol: `put(hash, bytes)`, `get(hash)`, `move_ref(name, hash)`,
  `list_refs(prefix)`. Implementations, all Protocol-conformant and all
  exercised by the default suite: `InMemoryStore` (the default, and the only
  one the invariant tests need), `FileStore` (persistent CLI/dashboard state),
  `SqliteStore` (persistent, inspectable, stdlib sqlite3).
  Both persistent backends are local and offline; there is no remote
  backend and no test depends on an external service.
- Refs: `agents/<name>/<state>` (mobile), `agents/<name>/v<semver>`
  (immutable - moving one raises), `topology/<version>`.
- Addresses are 64 lowercase hex, refused otherwise on BOTH `put` and `get`
  (`assert_object_address`, every backend). An address is an untrusted path
  component: `FileStore` turned one into a filename, so `get("../../x")` read a
  file outside the store. The route that reaches a store refuses it first.
- `StagedStore` is how invariant 3 is kept at the CLI: `cle build` seeds the
  components it resolves against, and seeding is a write, so the build runs
  against writes held in memory and `commit()`s only on success. A build that
  fails must leave the store byte-identical.
- Semver rule: major = trigger changed, minor = component ref swapped,
  patch = lifecycle thresholds only.
- Lifecycle states implemented in v1 (`STATE_RANK`): `archived`(0),
  `candidate`(1), `trial`(2), `ephemeral`(3), `pinned`(4) - **five**. The
  published part-7 machine names more (`pattern`, `deprecated`); those are NOT
  in the code. Do not reference them as if they were.
