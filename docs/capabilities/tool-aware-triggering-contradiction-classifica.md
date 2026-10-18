## 10. Tool-aware triggering & contradiction classification
- **Tools are declarations, never executions**: two-stage gating: resolve
  fails fast on a missing library tool or an unmounted trigger requirement;
  replay capture requires centroid match **AND** tool mount, with
  unmounted-tool episodes staying in the denominator so the capability gap is
  visible. `tool_result` is frozen decor: read to classify divergence, never
  asserted correct (*invariant 5*).

> **⚠ The four-contradiction taxonomy is INERT in a real embedding space.**
> Zero divergent pairs across all seven planted intents. Cosine measures
> **topical relatedness, not contradiction**: the planted *opposing* directives
> score 0.62–0.86 because they *are* about the same thing. v1 only appeared to
> detect contradictions through lexical accident. **No threshold rescues this**
>, the bar would need to exceed 0.86, flagging every pair; it needs a
> signed/entailment operator, which is its own run. The `world_state` question
> is **superseded, not answered**: the rule is unreachable because nothing
> registers as divergent. The taxonomy is valid **only for `stub:hashed64`**,
> and even there it is a lexical proxy.

- **Three-valued verdict**: `stable` / `unstable` / **`unavailable`**. An
  `unstable` cluster is **vetoed** (no candidate). `unavailable` is **not** a
  veto: the candidate is born carrying `stability="unavailable"`, surfaced at
  the human gate. Blocking on a check's absence would stop the first pillar
  producing anything at all. **A non-measurement must never masquerade as a
  verdict**: but it is a disclosed gap, not a silent pass.
- **Permanent attribution + resolution diagnostic**: the `cluster_stability`
  line always carries `world_state_attribution` (`ws_would_be_intra`,
  `ws_share_pct`) and a `resolution` flag marking a cluster `degenerate` when
  its divergent cosines are too concentrated to resolve a verdict. Diagnostic
  only, never blocking.
