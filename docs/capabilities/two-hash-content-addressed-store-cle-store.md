## 1. Two-hash content-addressed store (`cle/store`)
- **`content_hash`**: the single hashing function (canonical JSON, sha256).
- **Two hashes, always**: a candidate's `SourceSpec.hash` is never its built
  `Image.hash`; disjoint namespaces via a `cle_kind` domain marker. *Invariant 1.*
- **Verify-on-read integrity**: every fetched component is re-hashed; a
  mismatch logs `integrity_violation`, refetches once, and raises rather than
  ever injecting corrupt bytes. *Demo step 8.*
