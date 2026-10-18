## Every test file, and what it pins

| Area | Files (tests) | What they pin |
|---|---|---|
| Hashing & store | `test_content_hash` (6), `test_backends` (14), `test_sqlite_store` (37) | canonical JSON/sha256; Protocol conformance across backends; mobile vs immutable refs; an address that is not 64 hex characters is refused by every backend, on `put` and on `get`, before it becomes a path |
| Two-hash / tag targets | `test_tag_targets` (5) | source ≠ image namespaces; tags reject non-image |
| Integrity | `test_integrity` (4), `test_resolver` (5) | corrupt read → log + refetch + raise; resolve fails fast, writes nothing |
| Evidence types | `test_evidence_types` (6) | PreEvidence/Persistence rejected by the promotion gate at type level |
| Detection, episodes | `test_episodes` (21) | silence threshold both sides of the boundary; markers; closures; cold-start |
| Detection, clusters | `test_clustering` (6) | embed determinism/normalization; cosine bounds; disjoint vocab separates |
| Detection, signals | `test_signals` (10) | recurrence & reformulation relative to the user baseline, excl. abandoned |
| Embedder & provenance | `test_embedder_provenance` (10) | default is `CachedEmbedder`; miss raises; no test imports the live embedder; embedder swap changes `Image.hash`; cross-space compare raises; **cache-collapse integrity** |
| Build | `test_build_invariants` (6), `test_staged_failure` (3) | two-hash, determinism, probe-hash coverage, one log line; staged failure writes nothing |
| Replay & tools | `test_replay` (5), `test_replay_capability` (5), `test_tools_gating` (18) | both rates always computed; competition lowers capture; capture = centroid **AND** mount; tools declared, never executed |
| Contradiction taxonomy | `test_contradictions` (23), `test_stability_classifier` (4) | the four types + guards; `unavailable` births a candidate **with a disclosed gap**; `unstable` stays a hard veto; degeneracy diagnostic |
| Fixture realism | `test_fixture_realism` (14), `test_gdg_fixture` (11) | ≥8 distinct openers per *planted* intent; no sentence >15%; timing not single-valued; labels stay in the sidecar |
| Adversarial & demo | `test_adversarial_fixture` (1), `test_gdg_demo` (2) | a bridge yields non-trivial false-trigger; incumbent competition drops capture below 1.0 |
| Holdout discovery | `test_holdout_discovery` (2) | structural sanity in **both** eras (v1 stub, and the real embedder at its scoped threshold). Discovery **count and purity are reported, not gated**. Both run the **ungated** `detect_signal`, so no stability check executes and `Signal.stability` keeps its unexamined default, that field carries **no information** here |
| Oplog views & provenance | `test_oplog_views` (9) | every emitted op classifies into exactly one bucket (AST scrape); an unknown op raises; shadow lines are never rendered as a move; `on_behalf_of` is actually written at birth |
| Topology embedding key | `test_topology_embedding` (8) | the vector space is recorded at topology scope, inherited by later writes; a first write without it raises; an embedder with no calibration provenance raises |
| Runtime & Goodhart | `test_goodhart_boundary` (5), `test_runtime` (7) | Container has no metrics read path; mounts; switch cost carries both diffs |
| Lifecycle | `test_lifecycle` (9) | proof ladder & gate; a reason written only by the side that can conclude it, and never a decline reason on a tag move; shadow decides but never writes; topology chain/diff; revalidate holds then drifts, and a missing probe output counts as moved |
| Closed vocabulary | `test_closed_vocabulary` (10) | which VALUES may be written to `reason`; out-of-vocabulary raises, and there is no `other` bucket to absorb the distinction |
| CLI acceptance | `test_cli_acceptance` (11) | the documented commands run end to end on `--embedder stub`; an incumbent that cannot be loaded is warned about by exception type and does not stop the build |
| Embedder selection | `test_embedder_selection` (8) | which embedder the selection point returns for each flag and env var; a kind needing an external resource refuses by naming it, and a local space may not be selectable before it is calibrated |
| Vector contract | `test_vector_contract_bites` (13), `test_batch_guard` (9) | the three guards on the compare path fire per site, not merely exist; none of their refusals quotes the text it choked on |
| `CLE_VECTOR_CACHE` | `test_vector_cache_override` (4) | a cache pointed at a foreign space is refused, never silently consulted |
| Rate-limit backoff | `test_rate_limit_backoff` (11) | 429/`RESOURCE_EXHAUSTED` retries with full jitter; every other failure raises at once |
| Replay routing bar | `test_replay_routing_bar` (3) | the bar an opener is routed against is the SPACE's, resolved as the clusterer resolves it - an unscoped 0.6 published `false_trigger_rate 0.580` for months, invisible to a suite whose stub is calibrated at 0.6 |
| Logging | `test_logs` (17) | diagnostics go to stderr, never stdout, and a normal command writes nothing there; WARNING unless `CLE_LOG_LEVEL` asks; no file unless `CLE_LOG_FILE` names one, which rotates, and an unopenable one degrades to stderr; colour never reaches the record or the file and is decided per line; importing the package configures nothing, the entry points do; a formatter set on the handler is used rather than ignored; a probe is logged by position and a generator failure by type, never by text; a rate-limited retry is logged |
| Live revalidation | `test_live_revalidation_guard` (2) | revalidation against a live model cannot run inside the offline suite |
| Dashboard | `test_dashboard_routes` (40), `test_dashboard_matches_disk` (7) | every route; a write sent from another site is refused before any route runs; an object address that is not a hash is a 400, not a read; what a run carries out of a handler is three CLE variables, never the environment; and the API payload matches what is actually on disk, whitelist included |
| Unguarded-raise closures | `test_unguarded_raises` (10), `test_unguarded_contracts` (7), `test_refusals_bite` (13) | the raise sites the mutation sweep found unreachable, closed one at a time |
| Mutation harness | `test_mutation_harness` (12) | the tool that judges every other guard is itself judged: its pure functions are pinned |
| Frozen defects | `test_frozen_defects` (4) | defects measured and deliberately not fixed, pinned so they cannot change unnoticed |
| Published figures | `test_real_state_regression` (5) | recomputes numbers `docs/FINDINGS.md` publishes, so moving one turns the suite red |
| Space benches | `test_space_bench_metrics` (8) | which openers carry which planted intent (a mislabelling once halved a corpus silently), and that purity and completeness each reward the opposite degenerate grouping |
| Source-tree properties | `test_structural_guards` (9), `test_scripts_resolve` (40), `test_bench_imports_offline` (1) | docstring citations resolve, the documented suite count is true, scripts' imports resolve by AST - no script is executed |

| Level 2: the facet | `test_population_facet` (19) | what text may become a facet, the one construction module (AST), what a failed generation records |
| Level 2: privacy | `test_population_privacy` (22) | the distinct-user floor, the name screen on BOTH the raw and the shown form, the name cap, and the descriptions reaching the namer as fenced data |
| Level 2: grouping | `test_population_grouping` (6) | the explicit threshold wins over level 1's table, one embedding pass, the report quotes no facet |
| Level 2: topology | `test_population_topology` (11) | the facet as a typed field, only at birth, carried across tag moves; the reader refuses mixed spaces and duplicated instances |
| Level 2: end to end | `test_population_cli` (8) | three users build, `cle population` groups them; names only at the floor; a rebuild regenerates nothing; a refused read creates nothing in the path it was given |
| Level 2 board scripts | `test_level2_board` (2) | the adapter's refusals fire before anything bills or writes |

| Bucket measurement | `test_bucket_measurement` (7) | the rules `tools/buckets.py` classifies by: buckets 1 and 2 measured, bucket 3 declared and checked, SCOPE headers compared |

The rows sum to **578** across 57 files, against the **573** in the heading: the
difference is `test_real_state_regression`, whose 5 tests run only where the
private WildChat corpus is present and are therefore excluded from the
reproducible count. A file absent from this table is a file that does not exist.
