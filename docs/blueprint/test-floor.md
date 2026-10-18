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
  `uv run python tools/mutate.py` decides that by experiment, per site, and its own
  correctness is itself tested.
- **The suite owns its environment.** `$CLE_STORE`, `$CLE_EMBEDDER`,
  `$CLE_VECTOR_CACHE` and `$CLE_FORCE_REAL_MODEL` select backends and substrates
  at call time, and `.env` is re-read by any module that loads it, so a test
  session inherits the operator's shell unless it refuses to. It refuses: the
  variables are cleared and `load_dotenv` is neutralised for the session.
  Without that the suite is green on one machine and red on another, for a
  reason no test names.
