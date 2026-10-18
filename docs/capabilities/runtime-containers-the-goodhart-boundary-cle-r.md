## 5. Runtime, containers & the Goodhart boundary (`cle/runtime`)
- **Container**: a mutable record instantiating an image in a workspace, with
  **no** read path to its own metrics. *Invariant 2, enforced by reflection tests.*
- **Mounts**: ro/rw scopes; MCP handles as network mounts; rw store mounts must
  target mobile refs.
- **Metrics volume**: write-only `record()`; only the engine and the human read
  it, never the agent.
- **Context-switch cost**: every workspace image switch logs `diff_blocks` +
  `diff_tokens` (*legacy demo*: Δ 4 blk · 127 tok).
