## Why the facet has a contract

A *facet* is a descriptive text, written by the engine, that the population
layer embeds and groups. Apart from it, the only text in `topology.yaml` is an
agent name, typed by a human or written by a fixture.

The facet is **the first component in this project to produce prose by model
and store it**. Two properties of the codebase made a contract non-optional:

- `FreeTextInTopologyError` exists precisely to keep prose out of
  `topology.yaml`. A facet is prose. Adding it without a contract would reopen,
  by hand, the boundary the closed vocabulary shuts structurally.
- Clio embeds summaries of **conversations**; a facet is a summary of an
  **agent**, which is a more abstract object. Whether they group as well is
  measured in `docs/FINDINGS.md` §6 to §6d.

---
