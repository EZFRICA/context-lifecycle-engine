# CLE Test Accounting

What the suite covers, what a green run does and does not mean, and how the
count is kept honest.

The suite runs **offline**. No test needs a real model, an API key, or the
network: fingerprinters are stubbed and the detection embedder is
`CachedEmbedder` over committed vectors. A cache miss is an error, and a test
asserts that no test module imports the live embedder.

```bash
python -m pytest -q
```

A structural guard refuses any documented count that contradicts the collector.
That number had drifted six times before the guard existed, twice inside runs
written to fix the drift.

---

## Test coverage: **417 tests** across 44 files, 1 skipped

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
back. The run that comes out is byte-identical to the plain one — same count,
same duration — and reports success for a measurement that never happened.

That is deliberate: a suite that claims to be offline by construction must not
read the operator's credentials file at all. The consequence is that **there is
no flag that makes the suite live**, and a green run says nothing about a served
model.

Point the CLI at a live substrate instead. These read the variables the suite
refuses:

```bash
uv run cle build <src.yaml> --embedder real          # live embedding space
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
space. Classified by what the assertions depend on, not by whether an embedder
is merely instantiated:

| Bucket | Tests | Meaning |
|---|---|---|
> **⚠ These three numbers are a hand classification, not a measurement.** Two
> defensible mechanical readings of "classified by instantiation, not transitive
> import" were tried: at file level they give 138/124, at test-body level 26/189,
> and neither reproduces 161 / 60 / 31. The criterion also predates
> `open_embedder`, so it assumed no real embedder was reachable when three kinds
> are now selectable. The split should either be made mechanical and recomputed,
> or stop being presented as a measurement. It is left standing, labelled, until
> one of the two happens.

| **1. Embedder-agnostic** | **161** | No embedder in the assertion at all. Hashing, store/backends, integrity, resolver, evidence types, Goodhart boundary, staged failure, tag targets, lifecycle, episode segmentation, signals, and the fixture **data** properties. Hold in **any** era. |
| **2. Stub-as-a-tool** | **60** | Needs *some* deterministic embedder, but the claim is space-independent: two-hash inequality, build determinism, both rates always computed, tool gating, embedder provenance, runtime/switch cost, holdout structural sanity (both eras). |
| **3. Stub-as-the-subject** | **31** | True **only** in `stub:hashed64`; these do **not** describe the production system. The contradiction taxonomy, the stability property tests, the adversarial/demo exact rates, the directive-band check. |

**The good news is bucket 1: 161 of 417 assertions are invariant-core**: the
contract itself (two hashes, Goodhart, staged-failure, evidence types,
integrity) is entirely independent of which embedder is configured. Bucket 2
adds 60 whose claims survive an embedder swap.

Bucket 3 is the honest caveat: 31 tests pin the **v1 mechanism**, not the
production one. Every such module carries a SCOPE header saying so, notably
`test_stability_classifier.py`, whose four *hypothesis property* tests claim
generality by format while two of the claims are false under the real embedder.
They are kept, not weakened: they correctly pin v1.

| Area | Files (tests) | What they pin |
|---|---|---|
| Hashing & store | `test_content_hash` (6), `test_backends` (6), `test_sqlite_store` (37) | canonical JSON/sha256; Protocol conformance across backends; mobile vs immutable refs |
| Two-hash / tag targets | `test_tag_targets` (5) | source ≠ image namespaces; tags reject non-image |
| Integrity | `test_integrity` (4), `test_resolver` (5) | corrupt read → log + refetch + raise; resolve fails fast, writes nothing |
| Evidence types | `test_evidence_types` (6) | PreEvidence/Persistence rejected by the promotion gate at type level |
| Detection, episodes | `test_episodes` (19) | silence threshold both sides of the boundary; markers; closures; cold-start |
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
| Runtime & Goodhart | `test_goodhart_boundary` (5), `test_runtime` (6) | Container has no metrics read path; mounts; switch cost carries both diffs |
| Lifecycle | `test_lifecycle` (6) | proof ladder & gate; shadow decides but never writes; topology chain/diff; revalidate holds then drifts |

---

