## How the stages map to Clio

**The floor counts users, not clusters.** Clio sets its threshold on "the number
of unique users or conversations". A group is named only with at least 3 members
from at least 3 distinct users (`cle/population/privacy.py`). Below the floor a
group keeps its id and its place on the plot and loses its name, so the shape
stays visible and the vocabulary stays anonymous. The Stack Overflow export
carries the author id from the SQL to the view, which is what makes the floor
enforceable there; the recall figures never read that field, and the
cross-author constraint lives in the query.

**A screen on generated names.** Clio has a model verify its summaries before
display. The engine refuses mechanically instead, for the reason the facet
contract gives in §d: a prompt instruction is not a guard, and neither is a
second model's opinion of one. A name carrying a proper noun or a long number,
in its raw form or in the form shown, is dropped, and the group stays unnamed
rather than being named after somebody.

**The hierarchy - Clio's stage 4.** Group centroids are re-clustered, giving each
group a parent family. No corpus here has a labelled hierarchy, so the second
level's threshold is chosen structurally: reduce the count without one family
swallowing the corpus.

| gap | threshold | SO families (largest) | WildChat families (largest) |
|---:|---:|---|---|
| 0.02 | 0.76 | 337 (16) | 83 (23) |
| **0.04** | **0.74** | **310 (31)** | **71 (33)** |
| 0.06 | 0.72 | 271 (51) | 45 (58) |
| 0.10 | 0.68 | 155 (74) | 10 (**106**) |

At 0.10, WildChat puts 106 of 116 groups in one family - a collapse, not a
hierarchy. At the chosen 0.04, Stack Overflow's 367 groups become 310 families
(15.5% fewer) and WildChat's 116 become 71 (38.8% fewer): the reduction is
bounded by the singletons, since a group of one has nothing to be grouped with.
