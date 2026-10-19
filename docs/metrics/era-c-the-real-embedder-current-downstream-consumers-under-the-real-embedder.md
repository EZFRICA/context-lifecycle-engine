## Downstream consumers under the real embedder

Detail in `docs/METRICS-ERAS-AB.md`. Two consumers are affected and the
direction differs:

* **Contradiction classification goes fully blind.** Cosine measures topical
  relatedness, not contradiction, so the four type taxonomy detects nothing in a
  semantic space. The classifier reports `unavailable`, which is a disclosed
  gap, never a reassuring "stable".
* **`world_state` is superseded, not answered.** The question it was posed to
  settle stopped being the right question.
