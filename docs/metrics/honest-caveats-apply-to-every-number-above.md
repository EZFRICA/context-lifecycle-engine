## Honest caveats (apply to every number above)

- Replay tests the **trigger only**, never answer quality, and never the
  temporal period (`period_tested: false`).
- A fingerprint delta proves the **substrate changed**, not that the agent is
  broken.
- `capture_rate` is relative to the **current topology**, not an absolute.
- **Silence-demotion** is data-injected in v1; the loop is not closed.
- Demo closures are **synthetic** CLI sugar; real closures come from the detector.
- The **adversarial/demo source is still templated**, so every era-A number
  inherits that bias.
- `examples/gdg_demo.py`'s 1.000 → 0.600 competition and its 0.143 false-trigger
  are a **constructed window** with a **deliberately planted** bridge, engineered
  to show the machinery fires, not an emergent result.

---
