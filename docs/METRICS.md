# CLE Metrics, Fixture Eras

Every number the system produces on **fixtures**, with its provenance and the
test that pins it. Numbers measured on real corpora are in `docs/FINDINGS.md`;
the contract is `docs/BLUEPRINT.md`.

Written across three measurement runs, and **later runs invalidated earlier
numbers**. Read the era label before the figure.

| Era | Data | Embedder | Status |
|---|---|---|---|
| **A, legacy demo** | templated `make_fixture.py` | `stub:hashed64` @0.6 | still shipped as the demo; **not realistic usage** |
| **B, realistic data** | realistic freeze-once fixtures | `stub:hashed64` @0.6 | superseded for detection numbers |
| **C, real embedder** | same realistic fixtures | `google:gemini-embedding-2:768` @0.775 | **current** |

* **Where A/B and C disagree, C wins.**
* Numbers labelled by agent name are **era A**, on a templated source. Demo
  mechanics, not measured reality.
* A number with no era and no test name should be distrusted.

Suite: **573 tests across 56 files**, `uv run pytest -q`. Five more run only where the private WildChat corpus is present, so they are not counted here: a suite size a reader cannot reproduce is not a suite size. See
`docs/TESTING.md`.

---

- [Two headline findings](metrics/two-headline-findings.md) - The original fixtures repeated one identical opener per intent (the string
- [Eras A and B, superseded](metrics/eras-a-and-b-superseded.md) - Detail in `docs/METRICS-ERAS-AB.md`. The short version, because era C only
- [Era C, the real embedder (current)](metrics/era-c-the-real-embedder-current.md) - Substrate `google:gemini-embedding-2:768`, 768-dim MRL-truncated. **247 distinct
- [Three data sources, three roles](metrics/three-data-sources-three-roles.md) - Evaluating a detector on data generated with that detector's own geometry is a
- [Honest caveats (apply to every number above)](metrics/honest-caveats-apply-to-every-number-above.md) - temporal period (`period_tested: false`).
- [Known debt](metrics/known-debt.md) - YAMLs, the dashboard demo). It is the live-demo backbone and is excluded from
