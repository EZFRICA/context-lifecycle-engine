## Offline by construction
No test may need a key or the network. The detection embedder in tests is
`CachedEmbedder` over committed vectors: a cache miss is an ERROR, never a live
call. `RealEmbedder` is generation-only and must not be imported by any test
module (asserted). Fingerprinters are stubbed.
