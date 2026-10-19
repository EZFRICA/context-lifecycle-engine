## Era C, the real embedder (current)

Substrate `google:gemini-embedding-2:768`, 768-dim MRL-truncated. **247 distinct
fixture texts** embedded in 247 calls (84.2 s) and frozen to
`examples/vectors.google-gemini-embedding-2-768.json`. CI reads them through
`CachedEmbedder`; a miss raises `CacheMissError` and never recomputes.


- [Pinning key](era-c-the-real-embedder-current-pinning-key.md)
- [Measure A, the detector on an independent fixture (offline, free)](era-c-the-real-embedder-current-measure-a-the-detector-on-an-independent-fixtu.md)
- [Before / after (GDG, 246 episodes)](era-c-the-real-embedder-current-before-after-gdg-246-episodes.md)
- [Threshold sweep, a clean inverted U](era-c-the-real-embedder-current-threshold-sweep-a-clean-inverted-u.md)
- [Born-candidate purity, counts NEVER stand bare](era-c-the-real-embedder-current-born-candidate-purity-counts-never-stand-bare.md)
- [Downstream consumers under the real embedder](era-c-the-real-embedder-current-downstream-consumers-under-the-real-embedder.md)
- [What got WORSE](era-c-the-real-embedder-current-what-got-worse.md)
