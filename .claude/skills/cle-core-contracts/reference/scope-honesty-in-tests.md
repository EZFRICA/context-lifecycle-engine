## Scope honesty in tests
Every test module states the vector space its assertions hold in. Three buckets
(counts in docs/TESTING.md): **embedder-agnostic** (the invariant core),
**stub-as-a-tool** (stub incidental, claim space-independent), and
**stub-as-the-subject** (true ONLY in `stub:hashed64`). A bucket-3 module must
carry a SCOPE header and must not read as a general invariant - property tests
especially, since their format claims generality by itself.
