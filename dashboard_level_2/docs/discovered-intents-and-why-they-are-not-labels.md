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
