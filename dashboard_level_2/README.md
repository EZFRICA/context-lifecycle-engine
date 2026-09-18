# Level 2 cluster board

A single self-contained `index.html`. No server, no build step, no dependency at
view time: the data is embedded, so the file opens from disk.

```bash
open dashboard_level_2/index.html
```

Or serve the repo if your browser blocks local fonts:

```bash
uv run python -m http.server 8090   # then http://localhost:8090/dashboard_level_2/
```

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

## Discovered intents, and why they are not labels

Only GDG carries intents; a generator planted them. `discover_intents.py` supplies
the missing ones the way level 2 does - it runs the engine's `cle.population`
stages: group the facets with the engine's `IntentClusterer` at an explicit
threshold, name each group through the user floor and the identifier screen, then
build the hierarchy. Only the embedding and the namer run on BigQuery.

**A discovered intent is a hypothesis, not a label.** Nothing scores a method
against names the same pipeline produced; that would be circular. They exist so
the plot can be read, and so a reader can see what a population layer surfaces.

**The committed names came from `name-prompt-v1`.** The prompt now fences its
descriptions as data and states the answer format, which makes it
`name-prompt-v2` and puts that version in every `namer_id`. The names in
`data/*.json` predate it and are kept as they are: re-running `discover_intents.py`
bills a generation per group and would produce v2 names, which is a re-measurement
and not a repair. Nothing else on the board depends on the version - the groups,
the families and every figure come from the embedding and the threshold.

The default threshold is where the planted GDG intents group best:

| threshold | groups | purity | completeness | F |
|---:|---:|---:|---:|---:|
| 0.60 | 1 | 22% | 100% | - |
| 0.75 | 5 | 61% | 89% | 0.723 |
| **0.78** | **9** | **76%** | **80%** | **0.782** |
| 0.85 | 23 | 91% | 52% | 0.664 |
| 0.94 | 45 | 98% | 15% | 0.263 |

Purity alone would be a trap: 45 groups for 46 clusters is 98% pure and says
nothing. Completeness is what over-splitting destroys, so the two together choose.

The threshold is a parameter, and the share of singletons it leaves is a property
of the corpus at that value. At 0.78 Stack Overflow splits into 367 groups with
345 singletons and WildChat into 116 with 105: most real cross-user clusters have
no counterpart among 40 users, which is what the 0.34% figure predicts, seen from
the other end. Pass another value as the first argument to see another share.

What passes the user floor, counted in DISTINCT USERS because that is the unit
the floor counts:

* Stack Overflow, 6 groups - `javascript_debugging_tasks` (6), `php_debugging_tasks` (4), `python_debugging_tasks` (4), `ui_styling` (3), `javascript_debugging_issues` (3), `object_initialization_tasks` (3)
* WildChat, **0 groups**. Two are large enough to describe and come from two
  people each, so the floor suppresses their names - here as on the board.
* GDG, 4 groups - `event_planning_assistance` (10), `recurring_newsletter_drafting` (10), `event_venue_management` (7), `speaker_invitation_management` (6), which is the generator's own vocabulary coming back

## How the stages map to Clio

**The floor counts users, not clusters.** Clio sets its threshold on "the number
of unique users or conversations". A group is named only with at least 3 members
from at least 3 distinct users (`cle/population/privacy.py`). Below the floor a
group keeps its id and its place on the plot and loses its name, so the shape
stays visible and the vocabulary stays anonymous. The Stack Overflow export
carries the author id from the SQL to the view, which is what makes the floor
enforceable there; the recall figures never read that field, and the
cross-author constraint lives in the query.

**A screen on generated names.** Clio has a model verify its summaries before
display. The engine refuses mechanically instead, for the reason the facet
contract gives in §d: a prompt instruction is not a guard, and neither is a
second model's opinion of one. A name carrying a proper noun or a long number,
in its raw form or in the form shown, is dropped, and the group stays unnamed
rather than being named after somebody.

**The hierarchy - Clio's stage 4.** Group centroids are re-clustered, giving each
group a parent family. No corpus here has a labelled hierarchy, so the second
level's threshold is chosen structurally: reduce the count without one family
swallowing the corpus.

| gap | threshold | SO families (largest) | WildChat families (largest) |
|---:|---:|---|---|
| 0.02 | 0.76 | 337 (16) | 83 (23) |
| **0.04** | **0.74** | **310 (31)** | **71 (33)** |
| 0.06 | 0.72 | 271 (51) | 45 (58) |
| 0.10 | 0.68 | 155 (74) | 10 (**106**) |

At 0.10, WildChat puts 106 of 116 groups in one family - a collapse, not a
hierarchy. At the chosen 0.04, Stack Overflow's 367 groups become 310 families
(15.5% fewer) and WildChat's 116 become 71 (38.8% fewer): the reduction is
bounded by the singletons, since a group of one has nothing to be grouped with.

## The plot

Hand-drawn SVG: three PCA axes rotated orthographically by two sliders. The
third axis is real - it orders the draw and sizes the mark - and the markup is
readable rather than a black box.

Each plot is 560 × 420, in a two-column grid; the third method wraps onto its own
row at full width. Tooltips carry the author, the discovered group, the cluster
count and the family.

Colour stays at two hues - selected group in the panel's accent, everything else
receding. Seven categorical hues fail the palette validator on both themes, and
Stack Overflow has 367 groups, so a colour-per-group is not available.

## Rebuilding it

The exports and the discovery bill BigQuery; the build does not.

```bash
uv run python examples/bigquery/facet_crossuser_so_bench.py   # -> data/so_view.json
uv run python dashboard_level_2/export_real.py                # -> data/real_view.json
uv run python dashboard_level_2/export_view.py                # -> data/crossuser_view.json
uv run python dashboard_level_2/discover_intents.py           # groups, names, families
uv run python dashboard_level_2/build.py                      # data/ -> index.html
```

Any missing export is simply absent from the selector; the board never pretends
to have a corpus it does not.

`export_real.py` reads gitignored WildChat material. Without it the board falls
back to the synthetic view alone rather than pretending it has real data.

`export_view.py` needs the BigQuery setup in `docs/BIGQUERY.md`, plus the remote
model `gen_gemini_flash` for facet generation. `build.py` needs nothing but the
committed `data/` files, so the board can be rebuilt offline after a style change.

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

## What the numbers are, and are not

**Ground truth by construction.** `examples/make_multiuser.py` partitions the GDG
corpus into 12 synthetic users and every message carries its intent in
`thread_id`. A positive pair is two DIFFERENT users' clusters of the same planted
intent. Nothing was labelled by hand.

**An upper bound, never an estimate.** One generator, so two users sharing an
intent sit closer than two real users would. The inflation is **not uniform**: it
favours the text methods, which share the surface vocabulary a facet abstracts
away.

**The plot is an aid, not evidence.** The scatter is 768 dimensions projected
onto three PCA axes, rotatable with the two sliders. Three axes carry **33% of
the variance on the synthetic corpus and 11% on the real one** - better than two,
and still most of the structure is off screen. Rotate before believing a gap: a
separation that survives every angle means something, one that appears at a
single angle is a fact about the projection. The table is the measurement.

Depth is carried by dot size, nearer being larger, and a small three-axis gnomon
sits in each panel's corner so a rotation reads as a rotation rather than as the
cloud rearranging itself.

The benches behind all of it are `examples/bigquery/facet_crossuser_bench.py`
and `facet_crossuser_so_bench.py`; the figures are published with their pinning
keys in `docs/FINDINGS.md` §6b–§7.
