## Models (frozen unless stated)
- `SourceSpec(yaml_raw, hash)` - the candidate's source.
- `TriggerSpec(centroid, embedder_id, period)` - the ENTRYPOINT.
  `embedder_id` (`provider:model:dim`) is REQUIRED: a centroid is only
  meaningful inside the vector space that produced it, so an embedder swap
  invalidates centroids exactly as a model swap invalidates a fingerprint -
  one layer deeper, and this one touches agent IDENTITY. Cross-space
  comparison raises `SpaceMismatchError` (enforced in replay, where routing
  actually compares candidate vs incumbents). Deliberately NO `model_version`:
  the embedding API exposes no version signal distinct from the model id, and
  a placeholder would give false drift assurance.
- `Image(source_hash, resolved_refs, assembled_prompt, trigger,
  model_fingerprint, pre_evidence, probe_set, mounted_tools,
  probe_output_hashes, hash)` - built artifact. `hash` covers ALL fields.
  Tags attach here only. `mounted_tools` = declared capability names;
  `probe_output_hashes` lets the re-validator LOCALIZE drift.
- `Container(image_hash, workspace_id, mounts, metrics_volume_id)` - mutable
  record. MUST NOT expose any metrics read path (no method, property, or
  context injection). The runtime writes metrics through
  `metrics_volume.record(container_id, event)` - one-way.
- `PreEvidence(capture_rate, false_trigger_rate, historical_cost, window,
  semantic_trigger_tested, period_tested)` vs
  `Evidence(cost_ratio, occurrences, closure_tags)` vs
  `Persistence(fingerprint_at_build, fingerprint_now, probe_deltas)` -
  three distinct types. Functions gate on the exact type they need.
