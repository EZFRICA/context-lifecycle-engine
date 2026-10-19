## Topology records: two closed contracts

`topology.yaml` is written by `cle/lifecycle/topology.py` and nothing else (a
property test enforces the single writer). Two fields are constrained by TYPE,
not by a write-time filter, because a filter is bypassed by the next path
someone adds:

- **`reason` is a closed vocabulary** (`cle/lifecycle/reasons.py`). Passing
  `cause["reason"]` raises `FreeTextInTopologyError`; the only route in is
  `reason=TopologyReason(...)` over a `Literal`. Two axes, deliberately not one
  field: ENGINE (`substrate_drift`, `silence`) vs HUMAN (`cost_regression`), and
  DESCENT vs DECLINE (`engine_disagrees`, `defer`). `engine_disagrees` must stay
  isolable: it is a human who deferred to the engine, and aggregating it as an
  independent judgement is the Goodhart constraint at population scale. Free
  user text belongs to the oplog note, which level 2 never reads.
  A member with no producer gets REMOVED, not kept as a slot: `repeated_harm`
  went in R36 because no rule emits it.
- **`embedding` is an aggregation key**, at TOPOLOGY scope, never per agent.
  `EmbeddingConfig(embedder_id, cluster_threshold, calibration)`, supplied at
  the first write and inherited afterwards. A write declaring a different space
  raises `EmbeddingConfigMismatchError`; a first write with none raises
  `MissingEmbeddingConfigError`. Two instances at different thresholds do not
  birth the same agents from the same usage, so a report aggregating topologies
  without grouping on this key measures its own instrumentation.
