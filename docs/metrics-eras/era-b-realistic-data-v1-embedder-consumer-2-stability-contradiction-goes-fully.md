## Consumer 2, stability / contradiction goes fully blind

| figure | v1 | real |
|---|---|---|
| divergent pairs, all 7 intents | many | **0** |
| events band_width | 0.3381 | 0.0000 |
| events ws_share_pct | 35.5 | 0.0 |
| events intra_cluster pairs | 3 | 0 |
| every intent `unstable` | True | False (all) |

Planted **opposing** directive cosines, real vs stub:

| pair | real (min/mean/max) | below 0.35 | stub (mean) | below 0.35 |
|---|---|---|---|---|
| newsletter short↔long | 0.619 / 0.657 / 0.699 | **0/4** | 0.251 | 3/4 |
| venue diy↔ask-approval | 0.666 / 0.739 / 0.864 | **0/12** | 0.239 | 10/12 |
| events confirm↔reroute | 0.657 / 0.676 / 0.693 | **0/4** | 0.138 | 4/4 |

**This is the wrong operator, not a mis-set threshold.** v1 only appeared to
detect contradictions by accident: opposing instructions happen to use
different *words*, so lexical overlap was low. `venue_policy`'s over-flag from
era B disappears, but for the wrong reason: nothing is flagged at all.

Because the check is unsound here it returns `verdict="unavailable"`, which
does **not** block birth (BLUEPRINT §5b). Reversing an earlier block restored
the first pillar from **0** candidates to 6 (GDG) / 3 (holdout).
