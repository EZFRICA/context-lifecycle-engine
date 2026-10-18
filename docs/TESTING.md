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


## Test coverage: **573 tests** across 56 files, 1 skipped

Five more run only where the private WildChat corpus is present, so they are not counted here: a suite size a reader cannot reproduce is not a suite size. The skip is that corpus-gated module.

**No test needs a real model, an API key, or the network**: fingerprinters are
stubbed and the detection embedder is `CachedEmbedder` over committed vectors
(a miss is an error, and a test asserts no test module imports the live
embedder). CI runs the suite plus an offline `full_loop.sh` smoke.


- [Design constraints measured on real data](testing/design-constraints-measured-on-real-data.md) - Figures measured on real corpora live in `docs/FINDINGS.md`, each with its
- [The vector contract](testing/the-vector-contract.md) - Comparing two vectors is now a guarded operation, because it was not:
- [The suite cannot be aimed at a live model](testing/the-suite-cannot-be-aimed-at-a-live-model.md) - autouse fixture, and neutralises `dotenv.load_dotenv` so `.env` cannot put them
- [`open_embedder`: three vector spaces](testing/open-embedder-three-vector-spaces.md) - nothing else records.** `EmbeddingConfigMismatchError` forbids changing a

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
| **1. Embedder-agnostic** | **448** | No embedder ran for the test. Hashing, store and backends, integrity, resolver, evidence types, the Goodhart boundary, staged failure, lifecycle, episode segmentation, signals, the level 2 facet and privacy guards, the dashboard routes, logging, the structural guards. They hold in **any** vector space. |
| **2. Stub-as-a-tool** | **96** | An embedder ran, but the claim is space-independent: two-hash inequality, build determinism, both rates always computed, tool gating, embedder provenance, CLI acceptance, the level 2 end-to-end run. |
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

- [Every test file, and what it pins](testing/by-file.md) - one row per module; a file absent from it is a file that does not exist.

The 57 files split **14 under `tests/property/`** - `test_bench_imports_offline`, `test_build_invariants`, `test_closed_vocabulary`, `test_clustering`, `test_content_hash`, `test_evidence_types`, `test_goodhart_boundary`, `test_oplog_views`, `test_replay`, `test_scripts_resolve`, `test_stability_classifier`, `test_staged_failure`, `test_structural_guards`, `test_tag_targets` - and **43
under `tests/unit/`**.

---
