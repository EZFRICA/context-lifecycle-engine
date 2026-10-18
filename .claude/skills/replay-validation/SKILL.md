---
name: replay-validation
description: Rules for the replay validation stage of cle build and for the minimal detector (episodes, clusters, embedders, signals, stability). Use when implementing or reviewing cle/detect or cle/build/replay.py.
when_to_use: Working in cle/detect or cle/build/replay.py; changing episode segmentation, clustering, an embedder, a signal or the stability check; asking what replay proves and what it cannot.
---

# Replay Validation & the Minimal Detector

## Always true, no file needed

- **Replay proves a TRIGGER, never answer quality**, and never the temporal
  period (`period_tested` is always false in v1). Any wording implying
  otherwise is a defect, including in a comment.
- **`false_trigger_rate` is computed wherever `capture_rate` is.** One without
  the other is half a measurement: a detector collapsing everything scores
  perfectly on the first.
- **Capability-gated episodes stay in the DENOMINATOR.** An episode that needed
  a tool the candidate does not mount is a capture the candidate did not make;
  dropping it inflates the rate.
- **Every bar is the SPACE's**, resolved through `cluster_threshold_for`, never
  a config constant. Routing used an unscoped 0.6 while clustering used the
  calibrated value, and that one line published `false_trigger_rate 0.580` for
  months as a defect of the detector - see
  `tests/unit/test_replay_routing_bar.py`.
- **A cosine across two spaces is not a number.** Each operand carries its own
  `embedder_id`, checked at all three comparison sites.
- **Ties go to the incumbent**, so a candidate never silently annexes traffic
  that is already routed.

## Open when you touch that area

| area | file |
|---|---|
| what replay answers, and what it cannot | [what-replay-proves-and-what-it-cannot.md](reference/what-replay-proves-and-what-it-cannot.md) |
| the run itself: window, routing, outcome | [the-replay-run.md](reference/the-replay-run.md) |
| episodes, clusters, embedders, signals | [minimal-detector-v1-no-bocpd.md](reference/minimal-detector-v1-no-bocpd.md) |
| the stability gate and its three values | [stability-gating-cle-detect-stability-py.md](reference/stability-gating-cle-detect-stability-py.md) |
| which fixture plays which role, and why | [fixtures-three-sources-three-roles.md](reference/fixtures-three-sources-three-roles.md) |
| figures already measured - do not re-derive them | [measured-reality-do-not-re-derive-these-the-ha.md](reference/measured-reality-do-not-re-derive-these-the-ha.md) |
| cold start | [cold-start.md](reference/cold-start.md) |
