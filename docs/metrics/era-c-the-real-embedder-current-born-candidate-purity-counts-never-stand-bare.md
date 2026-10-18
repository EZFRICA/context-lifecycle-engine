## Born-candidate purity, counts NEVER stand bare

A bare count is the trap (cf. the holdout's spurious 0→1). Classification:
**GENUINE** = recall ≥0.8 and purity ≥0.8; **FRAGMENT** = purity ≥0.8, recall
<0.8 (a pure subset); **SPURIOUS** = purity <0.8 or no planted intent.

| fixture | born | GENUINE | FRAGMENT | SPURIOUS |
|---|---|---|---|---|
| GDG | 6 | **2**: `speakers` r0.92/p1.00, `agenda_workshop` r0.89/p1.00 | 2, `newsletter` r0.19/p1.00, `sponsors` r0.64/p0.90 | 2, a 20-episode agglomerate merging events+agenda_meetup+venue_policy (p0.45); a 3-episode noise recurrence (no intent) |
| holdout | 3 | **2**: `outreach` r0.89/p0.89, `meetup-prep` r0.89/p1.00 | 1, `venue` r0.56/p1.00 | 0 |

So the honest reading of "6 GDG candidates" is **2 genuine, 2 pure fragments, 2
spurious**: and both spurious ones would reach a human as proposals. That is
precisely why the disclosed-gap marker exists on the Births card. GDG's 2
genuine matches the sweep's 2/7 strict.

Note the holdout wording: earlier drafts said it "recovers 3/3". That
overstated it, 8/9, 8/8, 5/5 are **purity**; under recall *and* purity it is
**2 clean + 1 pure fragment**.

Also note what the holdout companion test does NOT report: it drives the
**ungated** `detect_signal`, so no stability check runs and the `Signal.stability`
it prints is an unexamined default (`stable`), not a measurement. It must not be
read against the `unavailable` verdict below, different code path, not a
contradiction.
