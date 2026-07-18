"""SourceSpec, Image, evidence types, and tag-target rules.

Contract (cle-core-contracts, BLUEPRINT §4-§5):
- `SourceSpec(yaml_raw, hash)` — the candidate's source, hashed as-is.
- `Image(source_hash, resolved_refs, assembled_prompt, trigger,
  model_fingerprint, pre_evidence, hash)` — the built artifact; `hash`
  covers ALL fields. Invariant 1: image.hash != source.hash, always.
- Lifecycle tags attach to Image hashes only; tagging a source hash raises
  `TagTargetError`.
- Three evidence types, distinct at type level (invariant 5):
  `PreEvidence` (replay, retrospective) / `Evidence` (trial, lived) /
  `Persistence` (re-validation, drift). A function expecting Evidence
  rejects PreEvidence.

Implemented in commits 3-4.
"""
