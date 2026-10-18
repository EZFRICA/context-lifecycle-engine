## The replay run
Inputs: candidate Image (trigger included), prompt history window (default
30d), current topology (A, B, C routing), the candidate's `mounted_tools`.
Procedure:
1. **Provenance gate** - the candidate's `embedder_id` must match every
   incumbent's, else `SpaceMismatchError`. Cosines across vector spaces are
   category errors, not small numeric ones.
2. Re-segment the window into episodes (v1: silence threshold + explicit
   markers; BLUEPRINT §9 decision 1).
3. For every episode, evaluate routing against topology ∪ {candidate}. An
   episode whose `requires_tool` is not in `mounted_tools` is NOT captured -
   but it STAYS IN THE DENOMINATOR, so capture drops honestly instead of
   hiding the capability gap. `tool_result` is frozen decor: readable, never
   asserted correct (that would be answer quality).
4. Report:
   - `capture_rate` = captured in-cluster episodes / total in-cluster episodes
   - `false_trigger_rate` = captured OUT-of-cluster episodes / total
     out-of-cluster episodes  ← must replay out-of-cluster traffic; a capture
     rate without a false-trigger rate is meaningless and fails review.
   - `historical_cost` = mean iterations of in-cluster episodes under the
     current topology (the birth justification number).
Determinism: same window + same candidate ⇒ same report (property test).
Replay touches no live traffic, no store writes except the build log.
