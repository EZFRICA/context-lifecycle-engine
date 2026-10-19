## What none of this proves


- Nothing here says an agent born this way is **useful**: grouping intents is
  not serving them, and the CLE tests triggers, never answers.
- 67% is one corpus, one moderator population, one language distribution, and
  every bench figure is conditioned on `gemini-embedding-001`.
- The false trigger rate of 0.580 was a defect of the MEASUREMENT PATH, found on
  2026-10-17 and fixed: replay routed at a space-independent 0.6 while the build
  clustered at the calibrated 0.775. It now reads 0.000, and what remains a
  defect is that this rate gates nothing at birth. The facet path is still a
  **pilot** integrated into nothing.
- **No ground truth exists for demotion.** Detection has an external check (a
  moderator closing one question as a duplicate of another is a judgment the
  detector never sees). Nothing plays that role for whether a demotion was
  correct, so lifecycle figures show the machinery running, not deciding well.
- **No figure here aggregates topology histories.** §6d does group real users
  with each other, so this file now carries population figures in the corpus
  sense. It carries none in the engine sense: that work reads generated facets
  and its own exports, never `topology.yaml`, and lives entirely outside `cle/`.
  The closed vocabulary, the embedding key and the provenance fields remain
  necessary-condition work - the conditions under which aggregating topologies
  would be safe, not an instance of it.

See `docs/METRICS.md` for fixture era numbers, `docs/CAPABILITIES.md` for components.
