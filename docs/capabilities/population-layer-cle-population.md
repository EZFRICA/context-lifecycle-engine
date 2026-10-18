## 12. Population layer (`cle/population/`)

Level 2 of the engine: it groups the agents of many users by what they do,
following Clio's four stages, and reads nothing but `topology.yaml` records.

- **The facet** (`facet.py`, `generator.py`): one sentence per agent, generated
  ONCE at the agent's birth by `cle build`, from the openers the replay
  attributed to its cluster, and stored in the topology entry as a typed field
  (`docs/proposals/facet-contract.md`). `Facet` is a frozen model that refuses a
  text outside 40-300 characters, or carrying a URL, a file path, a number longer
  than two digits or a capitalised non-initial token; the builder also refuses a
  six-word span copied from the source. It is constructed in one module,
  asserted by AST. `write_topology` accepts it only at birth and carries it
  across every later write of the agent. A failed generation records
  `facet_status: generation_failed` and the kind of failure, never the text; an
  agent born before facets carries no status and never gets one. The generator
  is a deterministic template for `stub-*` model ids, the configured model
  otherwise.
- **The reader** (`reader.py`): the only way in. The latest topology record of
  each instance, one instance per user. It refuses a directory with no topology,
  two instances born under different embedding configurations, and the same
  instance given twice, which would count one user as two.
- **Grouping and hierarchy** (`grouping.py`): the engine's `IntentClusterer`
  over facet vectors, at an EXPLICIT threshold that `IntentClusterer` honours
  over its per-space table; one embedding pass shared by both levels; the parent
  level at the threshold minus 0.04.
- **Naming and privacy** (`naming.py`, `privacy.py`): a group is named only with
  at least 3 members from at least 3 distinct users; a name is screened on its
  raw form and on the form shown; below the floor a group keeps its id and its
  size and loses its name. Deterministic namer, or the configured model.
- **The report** (`report.py`): group sizes, user counts, screened names,
  families. No facet text, no instance id.
- **CLI**: `cle population <state_dir>...` writes `report.json` and one
  `population_report` op line under `--out`, never into the instances it reads.
  `--threshold` is a parameter whose right value depends on the corpus
  (`docs/FINDINGS.md` §6d).
- **Pinned by** `test_population_facet`, `test_population_privacy`,
  `test_population_grouping`, `test_population_topology` and
  `test_population_cli`, offline; the last runs three users end to end through
  the CLI.
- **The single global floor is insufficient, and is known to be** (BLUEPRINT
  §7c): it is the floor that exists, not the one the problem requires.

`dashboard_level_2/` is the bench view of the same stages over three corpora
(Stack Overflow, WildChat, GDG) in BigQuery's vector space. Its grouping, floor,
screen and hierarchy are imported from `cle.population`; only the embedding and
the namer run on BigQuery. See `dashboard_level_2/README.md` for its numbers.

---
