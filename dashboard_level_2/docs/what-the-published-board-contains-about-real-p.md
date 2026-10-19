## What the published board contains, about real people

**A decision, taken knowingly, and reversible in one line.** `data/real_view.json`
is derived from real WildChat conversations: 130 facets from 40 users, each point
carrying a `user` field holding the first 8 characters of the pseudonym the corpus
itself ships (for example `0347a597`), and `build.py` inlines all of it into
`index.html`. Two things follow that a reader should not have to infer:

- **The three-distinct-user floor does not govern these points.** It governs
  which GROUPS may be named (`cle/population/privacy.py`). A facet shown on the
  plot passed the facet contract - length, no URL, no path, no long number, no
  capitalised non-initial token, no six-word verbatim span - and nothing else.
- **The facets are what the model wrote, unedited.** Mechanical redaction
  (`cle.population.leak.redact`) changed none of the 130, which says the screens
  found nothing to remove, not that a human read them.

The pseudonym is what makes the plot legible as a POPULATION - which points came
from one person is the whole claim of a cross-user view - and it is also the
field that lets two facets be joined back to one person. If that trade is not
one you want to publish, drop `user` from the export in `export_real.py`: the
grouping, the names, the families and every number on the page survive it, and
only the per-user colouring is lost.

Stack Overflow is a different case and needs no such decision: those identifiers
are public and already resolve to public profiles. Worth knowing rather than
discovering.
