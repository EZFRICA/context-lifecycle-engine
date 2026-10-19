## Test coverage

The count, the per area table, and the classification of what a green suite
actually validates are in `docs/TESTING.md`.

The one line worth repeating here: **the suite is offline**, and a green run
pins the contract, not the production vector space. How much of it holds in any
vector space, and how much pins only the v1 stub mechanism, is measured by
`tools/buckets.py` and checked in CI; the table is in `docs/TESTING.md`.

---
