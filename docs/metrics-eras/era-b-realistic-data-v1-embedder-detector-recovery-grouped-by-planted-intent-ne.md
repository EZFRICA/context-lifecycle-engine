## Detector recovery (grouped by *planted* intent, never by detected cluster)

| planted intent | occurrences | distinct openers | detected clusters |
|---|---|---|---|
| events | 10 | 10 | 9 |
| newsletter | 16 | 12 | 11 |
| speakers | 12 | 12 | 11 |
| sponsors | 14 | 12 | 10 |
| agenda_meetup | 9 | 8 | 6 |
| agenda_workshop | 9 | 8 | 4 |
| venue_policy | 8 | 8 | 8 |

63 clusters total; 22 reach the ≥3-occurrence signal gate, none mapping cleanly
to a planted intent. Under a strict criterion (one cluster holding ≥80% of an
intent **and** ≥80% pure), v1 recovers **0/7**: and that is its *best across a
full 0.40–1.10 sweep*, not just at 0.6. Lax (≥50%/≥50%): 1/7.
