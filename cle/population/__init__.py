"""Level 2 - the population layer, inside the engine.

Level 1 (`cle.detect`, `cle.build`, `cle.lifecycle`) turns ONE user's usage
into agents and moves them on lived evidence. Level 2 reads what level 1
recorded across MANY users' topologies and groups the agents that do the same
thing. It follows Clio's four stages:

  1. facet      `facet.py`, `generator.py` - one sentence per agent, generated
                ONCE at birth by `cle build` and stored in `topology.yaml` as a
                typed field (docs/proposals/facet-contract.md).
  2. grouping   `grouping.py` - the engine's own `IntentClusterer`, over facet
                vectors, at an explicit threshold.
  3. naming     `naming.py`, `privacy.py` - a name per group, shown only when
                enough DISTINCT users produced it, and only if it carries no
                identifier.
  4. hierarchy  `grouping.build_hierarchy` - the group centroids clustered
                again, one level up.

`reader.py` is the only way in: it reads `topology.yaml` records and nothing
else, which is the boundary BLUEPRINT §7b draws. `report.py` assembles the
output, and the output carries counts and screened names, never a facet's text.

This module imports nothing on purpose. `cle.lifecycle.topology` imports
`cle.population.facet`, and `cle.population.reader` imports
`cle.lifecycle.topology`; an eager import here would close that loop at import
time.
"""
