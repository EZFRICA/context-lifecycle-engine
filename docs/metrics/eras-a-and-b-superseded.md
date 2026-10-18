## Eras A and B, superseded

Detail in `docs/METRICS-ERAS-AB.md`. The short version, because era C only
makes sense against it:

* **Era A** (legacy templated demo): three clean agents, high capture, low false
  trigger. Those numbers came from `make_fixture.py` emitting templated text, not
  from detection working.
* **Era B** (realistic data, v1 embedder): the same detector on varied phrasing
  shattered every recurring intent into near singletons. Holdout discovery fell
  to **0**.

---
