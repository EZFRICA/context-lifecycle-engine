## d-bis. Two consequences of §c and §d, from the review

**The facet is DATA, not a derivation.** It cannot be recomputed from the
corpus, §c makes it a fixed point generated once, so it lives in the
append-only chain like everything else, and losing it means losing it. This is
the opposite of a centroid, which any run can rebuild from the same episodes.
Anything that treats facets as regenerable is wrong about them.

**Agents born before facets exist will never have one.** There is no
back-generation: their episodes are still in the store, but a facet generated
today from a cluster judged years ago would carry today's model and today's
prompt while claiming to describe that birth. That is the false-`Persistence`
shape, an artefact presented as a record of something it did not
witness.

So: **KNOWN DIVERGENCE, with a cut-off date**, recorded the same way as for the
topology records that keep a false cause. A population aggregate must be able to
tell "no facet because the agent predates facets" from "no facet because
generation failed", and that distinction has to be representable, not inferred
from a null. It is: a topology entry carries `facet_status: present` or
`generation_failed` (the kind of failure goes to the oplog, never the text), an
entry with no status predates facets, and the population report counts the two
apart.
