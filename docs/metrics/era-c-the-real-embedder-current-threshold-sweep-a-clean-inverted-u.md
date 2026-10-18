## Threshold sweep, a clean inverted U

| thr | clusters | recovered (strict) | events_false | events_capture |
|---|---|---|---|---|
| 0.600 | 2 | 0 | 0.6316 | 0.8106 |
| 0.650 | 3 | 0 | 0.0541 | 0.6699 |
| 0.700 | 13 | 1 | 0.2679 | 0.7051 |
| 0.750 | 33 | 1 | 0.0488 | 0.4634 |
| **0.775** | **40** | **2** | **0.0044** | **1.0000** |
| 0.800 | 51 | 1 | 0.0466 | 0.8000 |
| 0.850 | 80 | 0 | 0.0247 | 1.0000 |
| 0.900 | 91 | 0 | 0.0122 | 1.0000 |

Below ~0.70 purity collapses (recall ~1.0, purity ~0.0, everything merges);
above ~0.85 recall collapses (purity 1.0, recall 0.1–0.3, fragmentation).

**Adopted: 0.6 → 0.775**, scoped to `embedder_id` (0.6 stays correct for
`stub:hashed64`); `CLUSTER_THRESHOLD_BY_EMBEDDER` in `cle/detect/clusters.py`.

> **What that 0.775 actually rests on.** The GDG sweep peak is **in-sample** -
> 0.775 was *chosen* on the fixture it is then scored against, so the 2/7 is not
> independent evidence. The credible support is the **holdout**:
> process-independent, authored without knowledge of the embedder, and never
> consulted to pick the threshold. That is **a single independent confirmation
> point**: one holdout, one threshold, one embedder. It justifies adopting
> 0.775 over 0.6; it does not establish 0.775 as calibrated in general.
> *Now pinned by `test_holdout_discovery.py::test_holdout_discovery_on_the_default_embedder`.*
