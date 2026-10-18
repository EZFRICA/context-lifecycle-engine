## Level 2 board

`open dashboard_level_2/index.html` - the same stages, run by the engine's code
over three bench corpora in BigQuery's vector space. Self-contained, no server,
no build step. Three sources behind one selector:

| source | real users | labels | what it can answer |
|---|---|---|---|
| Stack Overflow, cross-author | yes | yes, moderator duplicates | recall at a matched false-positive rate |
| WildChat, 40 users, 130 clusters | yes | no | what the layer actually sees |
| GDG, 12 synthetic users | no | yes, planted intents | purity and completeness, hence calibration |

It shows the two candidate architectures at parity - raw episodes against
generated facets - with what each buys and what it costs, and it does not pick
one: the ranking reverses with the error budget (`docs/FINDINGS.md` §6c), so the
choice belongs to whoever sets that budget.

The floor and the screen are the engine's: on WildChat no group reaches 3
distinct users, so the corpus names nothing at all. The numbers are in
`dashboard_level_2/README.md`.

---
