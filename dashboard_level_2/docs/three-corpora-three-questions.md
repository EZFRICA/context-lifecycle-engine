## Three corpora, three questions

A selector switches between them. They are not interchangeable and the page says
so.

| corpus | what it is | what it can answer |
|---|---|---|
| **Stack Overflow** | 3,000 cross-author pairs a moderator ruled on | recall, on real users with real labels. The strongest evidence here |
| **WildChat** | 130 clusters, 40 real users, real prompts and facets | what level 2 would see. No labels, so no recall |
| **GDG synthetic** | 12 users from `make_multiuser.py`, intent in `thread_id` | recall and purity, but the users come from one generator |

WildChat, having no labels, can only report that facets surface 135 cross-user
pairs above cosine 0.7 against raw text's 19 - which admits two readings: facets
recover structure raw text misses, or facets over-merge.

**Stack Overflow settles it.** With real users and real rulings, raw text leads at
every budget (61.1% against 54.8% for the redacted facet at 10.1% FP). Surfacing
more candidates is not finding more matches. Both labelled corpora agree on the
ordering; the synthetic one overstates the gap, 21.4 points against 6.3.
