# CLE Test Accounting

What the suite covers, what a green run does and does not mean, and how the
count is kept honest.

The suite runs **offline**. No test needs a real model, an API key, or the
network: fingerprinters are stubbed and the detection embedder is
`CachedEmbedder` over committed vectors. A cache miss is an error, and a test
asserts that no test module imports the live embedder.

```bash
uv run pytest -q
```

A structural guard refuses any documented count that contradicts the collector.
That number had drifted six times before the guard existed, twice inside runs
written to fix the drift.

---

## Test coverage: **521 tests** across 53 files, 1 skipped

Five more run only where the private WildChat corpus is present, so they are not counted here: a suite size a reader cannot reproduce is not a suite size. The skip is that corpus-gated module.

**No test needs a real model, an API key, or the network**: fingerprinters are
stubbed and the detection embedder is `CachedEmbedder` over committed vectors
(a miss is an error, and a test asserts no test module imports the live
embedder). CI runs the suite plus an offline `full_loop.sh` smoke.

### Design constraints measured on real data

Figures measured on real corpora live in `docs/FINDINGS.md`, each with its
pinning key and its reproduction command. Four constraints came out of that work
and must survive any redesign:

1. **The signal is a tail effect, never a mean.** An aggregator reading mean
   similarity sees ~0.55 everywhere and concludes nothing.
2. **No dedicated vector storage is justified at this scale.** Exhaustive search
   stays under 3 s at one million vectors.
3. **Reformulation false positive rates are UPPER BOUNDS.** A control pair is one
   no moderator closed, which is the absence of a judgment, not a judgment of
   distinctness.
4. **Three vector spaces exist**, and `bigquery:gemini-embedding-001:768` is a
   different model from the CLE's, not a different surface onto the same one.
   Cosine between them on the same texts: 0.040084.

### The vector contract

Comparing two vectors is now a guarded operation, because it was not:

- **`cosine` is a cosine, measured, not assumed.** Both shipped embedders
  return vectors of norm exactly 1.0 (measured, n=200 texts each), so the dot
  product is the cosine and the 0.6 / 0.775 thresholds share one scale.
- **`DimensionMismatchError`**: `zip` used to truncate to the shorter vector, so
  a 64-d stub centroid compared against a 768-d real embedding returned
  `-0.012148` and raised nothing. Unequal lengths now raise.
- **Space identity on the capture path**: `run_replay` refuses to run when the
  embedder's `embedder_id` differs from the trigger centroid's. The guard is on
  IDENTITY, not on dimension: two distinct real spaces of equal width would pass
  a length check and mean nothing.

**What the guard structurally cannot see.** `TriggerSpec.require_same_space`
compares two *stored* centroids and never sees the embedder actually running -
that was the gap. The new check closes it at the entry to `run_replay`, which
covers the three comparison sites inside it (`replay.py` selecting the target
cluster, computing capture, and beating incumbents) **only because every
centroid reaching them comes from the embedder checked at entry**. That is true
today; it is a flow property, not a structural one, and it would need
re-checking if a centroid ever entered by another path.

**Three sites, not one.** The first was found because a measurement happened to
cross it. The other two were found only by going looking. What an audit
finds is bounded by the pattern it searches for.

### The suite cannot be aimed at a live model

`CLE_EMBEDDER=real uv run pytest` looks like it works and measures nothing.
`tests/conftest.py` pops `CLE_EMBEDDER`, `CLE_STORE`, `CLE_VECTOR_CACHE`,
`CLE_STATE_DIR`, `CLE_ACTOR` and `CLE_FORCE_REAL_MODEL` in a session-scoped
autouse fixture, and neutralises `dotenv.load_dotenv` so `.env` cannot put them
back. The run that comes out is byte-identical to the plain one - same count,
same duration - and reports success for a measurement that never happened.

That is deliberate: a suite that claims to be offline by construction must not
read the operator's credentials file at all. The consequence is that **there is
no flag that makes the suite live**, and a green run says nothing about a served
model.

Point the CLI at a live substrate instead. These read the variables the suite
refuses:

```bash
uv run cle --embedder real build <src.yaml>          # live embedding space
uv run cle revalidate <agent> --model-id current     # live fingerprint probe
CLE_FORCE_REAL_MODEL=1 ./examples/full_loop.sh       # raises instead of falling back
```

The last one matters most: `CLE_FORCE_REAL_MODEL=1` makes the fingerprinter raise
on a failed probe rather than fall back to an offline hash, so a green run there
cannot be an offline run wearing a live label.

### `open_embedder`: three vector spaces

| kind | space | cost | reach |
|---|---|---|---|
| `stub` (default) | `stub:hashed64` | free | any text |
| `cached` | `google:gemini-embedding-2:768` | **free** | the 247 cached texts; a miss is `CacheMissError` |
| `real` | `google:gemini-embedding-2:768` | **one call per text, no cache consultation** (91 messages ≈ 32 s) | any text |

`cached` and `real` share an `embedder_id`: same geometry, different delivery.

**The default stays `stub`, and adopting the real embedder is expensive in a way
nothing else records.** `EmbeddingConfigMismatchError` forbids changing a
topology's vector space in place, deliberately, since centroids are only
meaningful in the space that produced them. So switching to the real embedder
means **abandoning the entire accumulated lifecycle history** and starting a new
one. That is the real cost of the migration, and it is not a bug.

The four example agent specs are regenerated by `examples/make_fixture.py` and
carry `trigger.embedder_id: stub:hashed64`. They are **era A**: that generator
imports the detector and treats "distinct vocabularies → distinct centroids" as
a design goal, so the fixtures share the assumptions of the system under test.
Under `--embedder cached` or `real` they now fail loudly rather than producing a
cross-space number.

### What the suite actually validates, by embedder dependence

A green suite does **not** mean every assertion holds in the production vector
space. The suite is split by what each test depends on, and the split is
MEASURED, not counted:

```bash
uv run python tools/buckets.py           # the table
uv run python tools/buckets.py --check   # CI: this table and every SCOPE header must agree
```

The suite runs once with a probe (`tests/conftest.py`, registered as a plugin)
that records which embedder each test invokes: in its body, in any fixture it
depends on, and at the import of its module. Buckets 1 and 2 follow from that
record. Bucket 3 is declared with the `stub_only` marker, because "true only in
the stub space" is a statement about what an assertion means, which no probe can
observe; the probe then checks that every marked test really did embed in
`stub:hashed64`, and reports the marker as false if it did not.

| Bucket | Tests | Meaning |
|---|---|---|
| **1. Embedder-agnostic** | **398** | No embedder ran for the test. Hashing, store and backends, integrity, resolver, evidence types, the Goodhart boundary, staged failure, lifecycle, episode segmentation, signals, the level 2 facet and privacy guards, the dashboard routes, the structural guards. They hold in **any** vector space. |
| **2. Stub-as-a-tool** | **94** | An embedder ran, but the claim is space-independent: two-hash inequality, build determinism, both rates always computed, tool gating, embedder provenance, CLI acceptance, the level 2 end-to-end run. |
| **3. Stub-as-the-subject** | **29** | Declared `stub_only`, and checked: true **only** in `stub:hashed64`, so they do **not** describe the production system. The contradiction taxonomy, the stability property tests, the adversarial and demo exact rates, the directive-band check. |

Bucket 1 is the contract itself: it holds whatever embedder is configured.
Bucket 3 is the caveat: those tests pin the **v1 mechanism**, not the production
one, notably `test_stability_classifier.py`, whose four *hypothesis property*
tests claim generality by format while two of the claims are false under the
real embedder. They are kept, not weakened: they correctly pin v1.

**What the probe cannot see.** Only embedders invoked inside the test process. A
test that embedded in a subprocess would measure as bucket 1. The four
subprocesses the suite starts collect the suite, print `cle --help`, import the
bench modules, and run `sleep` under bash to test an abort; none of them embeds.

| Area | Files (tests) | What they pin |
|---|---|---|
| Hashing & store | `test_content_hash` (6), `test_backends` (6), `test_sqlite_store` (37) | canonical JSON/sha256; Protocol conformance across backends; mobile vs immutable refs |
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
| CLI acceptance | `test_cli_acceptance` (10) | the documented commands run end to end on `--embedder stub` |
| Embedder selection | `test_embedder_selection` (6) | which embedder the selection point returns for each flag and env var |
| Vector contract | `test_vector_contract_bites` (12), `test_batch_guard` (9) | the three guards on the compare path fire per site, not merely exist |
| `CLE_VECTOR_CACHE` | `test_vector_cache_override` (4) | a cache pointed at a foreign space is refused, never silently consulted |
| Rate-limit backoff | `test_rate_limit_backoff` (11) | 429/`RESOURCE_EXHAUSTED` retries with full jitter; every other failure raises at once |
| Live revalidation | `test_live_revalidation_guard` (2) | revalidation against a live model cannot run inside the offline suite |
| Dashboard | `test_dashboard_routes` (34), `test_dashboard_matches_disk` (7) | every route; a write sent from another site is refused before any route runs; and the API payload matches what is actually on disk, whitelist included |
| Unguarded-raise closures | `test_unguarded_raises` (10), `test_unguarded_contracts` (7), `test_refusals_bite` (13) | the raise sites the mutation sweep found unreachable, closed one at a time |
| Mutation harness | `test_mutation_harness` (12) | the tool that judges every other guard is itself judged: its pure functions are pinned |
| Frozen defects | `test_frozen_defects` (4) | defects measured and deliberately not fixed, pinned so they cannot change unnoticed |
| Published figures | `test_real_state_regression` (5) | recomputes numbers `docs/FINDINGS.md` publishes, so moving one turns the suite red |
| Source-tree properties | `test_structural_guards` (9), `test_scripts_resolve` (38), `test_bench_imports_offline` (1) | docstring citations resolve, the documented suite count is true, scripts' imports resolve by AST - no script is executed |

| Level 2: the facet | `test_population_facet` (19) | what text may become a facet, the one construction module (AST), what a failed generation records |
| Level 2: privacy | `test_population_privacy` (21) | the distinct-user floor, the name screen on BOTH the raw and the shown form, the name cap |
| Level 2: grouping | `test_population_grouping` (6) | the explicit threshold wins over level 1's table, one embedding pass, the report quotes no facet |
| Level 2: topology | `test_population_topology` (11) | the facet as a typed field, only at birth, carried across tag moves; the reader refuses mixed spaces and duplicated instances |
| Level 2: end to end | `test_population_cli` (8) | three users build, `cle population` groups them; names only at the floor; a rebuild regenerates nothing; a refused read creates nothing in the path it was given |
| Level 2 board scripts | `test_level2_board` (2) | the adapter's refusals fire before anything bills or writes |

| Bucket measurement | `test_bucket_measurement` (7) | the rules `tools/buckets.py` classifies by: buckets 1 and 2 measured, bucket 3 declared and checked, SCOPE headers compared |

The rows sum to **526** across 54 files, against the **521** in the heading: the
difference is `test_real_state_regression`, whose 5 tests run only where the
private WildChat corpus is present and are therefore excluded from the
reproducible count. A file absent from this table is a file that does not exist.

The 54 files split **14 under `tests/property/`** - `test_bench_imports_offline`, `test_build_invariants`, `test_closed_vocabulary`, `test_clustering`, `test_content_hash`, `test_evidence_types`, `test_goodhart_boundary`, `test_oplog_views`, `test_replay`, `test_scripts_resolve`, `test_stability_classifier`, `test_staged_failure`, `test_structural_guards`, `test_tag_targets` - and **40
under `tests/unit/`**.

---

