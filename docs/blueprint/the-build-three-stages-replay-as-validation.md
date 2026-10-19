## 3. The build, three stages, replay as validation

Need: agents born from usage have no a-priori eval suite; their own history is
the suite. (APU lineage: this generalizes the Living DLL's block auto-detection
- observe, propose, confirm, from memory blocks to whole agents.)

1. **Resolve**: every `#ref` exists in the store. Missing ref fails the build
   in ms; nothing consumed. Extended: declared tools must resolve and be of
   kind `tool`, and a trigger's required capability must be mounted.
2. **Replay-validate**: replay the prompt history (window: `--replay-window`,
   default 30d) against the topology augmented with the candidate. Outputs:
   - `capture_rate`: fraction of the cluster's episodes the candidate's
     trigger would have intercepted;
   - `false_trigger_rate`: legitimate A/B/C traffic the candidate would have
     stolen (measured by replaying out-of-cluster episodes too);
   - `historical_cost`: mean iteration cost of the cluster under the current
     topology (the numeric justification of the birth).
   Replay validates the TRIGGER only, outputs are tagged `pre_evidence`.
   Answer quality is not and cannot be replay-tested (yesterday's user cannot
   rate an alternative answer).
3. **Assemble**: compile the system prompt in declared order, capture
   `model_fingerprint` (API version if exposed; else output hash over a fixed
   probe set), hash the complete artifact → Image.
