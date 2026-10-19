# CLE, System Capabilities

What the Context Lifecycle Engine does, why, and where each capability is
demonstrated. Two cardinal pillars, **detection** (agents emerge from usage)
and **lifecycle** (they earn or lose standing on lived evidence), over a
content-addressed store, a runtime, and a live dashboard. Pinned by the
**573-test** suite unless noted.

> ## ⚠ Read this before any number below
>
> This document describes **mechanisms**. How well they work on realistic data
> was measured separately (`docs/METRICS.md`), and the answers change what the
> numbers mean:
>
> **1. v1 detection only clustered because the fixtures were templated.** Given
> genuinely varied phrasing, the v1 bag-of-tokens embedder shattered every
> recurring intent into near-singletons; holdout discovery fell to **0**.
>
> **2. A real embedding model helps, but is not a drop-in.** At the old 0.6
> threshold it over-merges into 2 clusters and `false_trigger` jumps
> 0.061 → 0.632 (events intent, ideal centroid). Recalibrated to **0.775**
> (scoped to `embedder_id`) it beats v1, but GDG recovery tops out at **2/7**,
> and of the 6 candidates it births only **2 are genuine** (2 fragments,
> 2 spurious).
>
> **3. It breaks contradiction detection.** Cosine measures topical
> relatedness, not contradiction, so the four-type taxonomy (§10) detects
> nothing in a semantic space. The classifier reports `unavailable` there -
> a disclosed gap, never a reassuring "stable".
>
> Numbers attributed to `weekly_recap` / `standup_digest` / `incident_triage`
> and to `examples/full_loop.sh` come from the **legacy templated demo source**
> (`make_fixture.py`), labelled *legacy demo* throughout.

---


- [1. Two-hash content-addressed store (`cle/store`)](capabilities/two-hash-content-addressed-store-cle-store.md) - `Image.hash`; disjoint namespaces via a `cle_kind` domain marker. *Invariant 1.*
- [2. Detection, the first pillar (`cle/detect`)](capabilities/detection-the-first-pillar-cle-detect.md) - inter-message gap, floor 30 min) and explicit markers. Closure classification
- [3. Three-stage build (`cle/build`)](capabilities/three-stage-build-cle-build.md) - milliseconds having written nothing. *Invariant 3.*
- [4. Replay validation, trigger, never answer (`cle/build/replay.py`)](capabilities/replay-validation-trigger-never-answer-cle-bui.md) - intercept **against the current topology**; an incumbent owning part of the
- [5. Runtime, containers & the Goodhart boundary (`cle/runtime`)](capabilities/runtime-containers-the-goodhart-boundary-cle-r.md) - **no** read path to its own metrics. *Invariant 2, enforced by reflection tests.*
- [6. Lifecycle, the second pillar (`cle/lifecycle`)](capabilities/lifecycle-the-second-pillar-cle-lifecycle.md) - ephemeral(3) → pinned(4)`. Transitions are not an enumerated set: `move_tag`
- [7. CLI (`cle …`)](capabilities/cli-cle.md) - `build · run · ps · tag · log · diff · revalidate · decline · dashboard · clean`.
- [8. Live dashboard (`dashboard/`)](capabilities/live-dashboard-dashboard.md) - FastAPI + SSE + a single Alpine page (no build step). Four zones, **Pulse**
- [9. Embedder substrate & centroid provenance (`cle/detect/embedders.py`)](capabilities/embedder-substrate-centroid-provenance-cle-det.md) - google-genai adapter, **generation-only**: the sole thing needing a key and
- [10. Tool-aware triggering & contradiction classification](capabilities/tool-aware-triggering-contradiction-classifica.md) - fails fast on a missing library tool or an unmounted trigger requirement;
- [11. Fixtures, freeze-once, with an anti-templating guard](capabilities/fixtures-freeze-once-with-an-anti-templating-g.md) - (**rejection**), holdout (**discovery**, process-independent: it imports
- [12. Population layer (`cle/population/`)](capabilities/population-layer-cle-population.md) - Level 2 of the engine: it groups the agents of many users by what they do,
- [Test coverage](capabilities/test-coverage.md) - The count, the per area table, and the classification of what a green suite
- [What the numbers do NOT prove](capabilities/what-the-numbers-do-not-prove.md) - carried but not tested.
