## 1. Scope of v1

**In, both pillars, vertical slices:**
- Minimal detector: intent clustering (embedding of episode opener,
  incremental) + recurrence/reformulation counting per cluster, per-user
  baselines. No BOCPD (that's a v2 refinement of segmentation, not the
  introduction of detection).
- Three-stage build with replay validation (see §3).
- Two-hash Merkle store extension.
- Runtime: image/container split, mounts, Goodhart-bounded metrics volume.
- Lifecycle: tags (mobile states + immutable versions), engine in shadow mode,
  `topology.yaml` writer, re-validator.
- CLI: `cle build|run|ps|tag|log|diff` (shipped also: `revalidate`, `decline`,
  `dashboard`, `clean`).

**Out (stub interfaces only):** BOCPD segmentation, auto-approval of
all-pinned candidates, registry, cross-host runtime spec.
