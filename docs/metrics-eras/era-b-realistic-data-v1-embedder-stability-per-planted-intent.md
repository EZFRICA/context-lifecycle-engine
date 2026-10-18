## Stability per planted intent

| intent | unstable | resolution | band_width | ws_share_pct | ws_would_be_intra |
|---|---|---|---|---|---|
| events (tool) | True | resolved | 0.3381 | 35.5 | 2 |
| newsletter | True | resolved | 0.3474 | 0 | 0 |
| speakers (tool) | True | resolved | 0.2691 | 0 | 0 |
| sponsors (tool) | True | resolved | 0.3464 | 0 | 0 |
| agenda_meetup | True | resolved | 0.1760 | 0 | 0 |
| venue_policy | True | resolved | 0.3354 | 0 | 0 |

The degenerate `band_width = 0.0000` of the templated era was purely an
artifact. But note the **over-flag** side: with realistic follow-up variety the
classifier reads lexical spread as "divergence", so `venue_policy`'s genuine
temporal evolution is flagged unstable and its candidate suppressed. The same
embedder limitation, one layer down.
