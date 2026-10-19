## What it is for

The CLE's question is not how to create agents - there is no shortage of those -
but whether the agents that already exist still earn their standing. Level 2
answers that across a population: if one person's agent has a counterpart in
eleven other topologies, it is a shape the population keeps producing. If it
stands alone, its value has to come from somewhere else.

Level 2 runs in the engine (`cle/population/`, `cle population`). This board is
its bench view: the same stages, run by the same code, over three corpora whose
facets were embedded in BigQuery's vector space.

Grouping is the measurement underneath that decision. The board exists to make
the two candidate architectures **comparable, not ranked** - the constraint that
separates them (may the population layer hold user text?) belongs to whoever
deploys it.

| architecture | recall @10.1% FP | what level 2 stores |
|---|---:|---|
| read the episodes | 90.7%, identical every run | the episodes themselves |
| read a generated facet, redacted | 69–76% over five generations | one sentence, 0.00 proper nouns |

Both columns carry their strengths and their weaknesses on the page. The facet
rows depend on the draw of the generation: over five generations of the same 46
clusters, facet-redacted recall spans 69.3–76.4 at the 10.1% budget and
18.6–32.1 at 1% (`docs/FINDINGS.md` §7). The text rows are identical to the
decimal every time. The spread is read at the error budget whoever deploys the
layer sets, and it never re-rolls a lifecycle decision in the engine, where a
facet is generated once, at the agent's birth. The board renders the generation
the committed `data/crossuser_view.json` carries.
