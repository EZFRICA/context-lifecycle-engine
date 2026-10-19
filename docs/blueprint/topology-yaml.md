## 7. topology.yaml

Written only by `lifecycle/topology.py`. Every change is a commit in the same
DAG under a `topology/` ref prefix (one store, one audit trail, decision 2 of
v1 blueprint, settled). Entries carry the evidence (or pre_evidence at birth)
that caused them. `cle log topology.yaml` renders the history with provenance,
approvals, and numbers; `cle diff` renders the learned-topology delta.

The record also carries **`embedding`**, at TOPOLOGY scope and never per agent:
the `embedder_id`, the cluster threshold, and where that threshold came from. It
is supplied at the first write and inherited afterwards, and a later write that
declares a different space is refused rather than allowed to inherit silently.

This is an AGGREGATION KEY, not metadata. Two instances running the same
embedder at different thresholds do not birth the same agents from the same
usage, so a topology history without this field is comparable to nothing, and a
population report that aggregated it anyway would measure its own
instrumentation. Any reader of the history, the dashboard included, must be able
to see it.

### 7b. The boundary free text does not cross

`topology.yaml` is the only file the population level reads
(`cle/population/reader.py`). Two fields
could carry a descent's motive across it, and they are separated by TYPE, not
by a write-time filter, a filter is bypassed by the next path someone adds:

| field | where it lives | who reads it | shape |
|---|---|---|---|
| `reason` | `topology.yaml` **and** the oplog | user + population level | closed vocabulary (`cle/lifecycle/reasons.py`) |
| `note` | the oplog only | the user, locally | free text |

The vocabulary is split on two axes, deliberately not merged into one field:
**engine-authored** (`substrate_drift`, `silence`: a metric
fired) versus **human-authored** (`cost_regression`: somebody judged); and
**descent** versus **decline** (a decline says the detection was right and the
moment was not, counting it as a rejection would be a product contresens).
`engine_disagrees` is human but stays isolable, so an aggregate claiming to
measure independent human judgement can exclude the engine's own influence.

Both axes are enforced where a reason is written, not only named: a tag move
refuses a decline reason, only an `engine:` actor may write an engine-authored
reason and only a non-engine actor a human-authored one
(`cle/lifecycle/tags.py`), and `cle decline` accepts decline reasons alone.

Out-of-vocabulary values raise (`UnknownReasonError`); there is no `other`
bucket, which would silently absorb the distinction the field exists to make.
`cluster_stability`'s `reason=` is a technical diagnostic on a technical op and
is explicitly exempt, a coincidence of keyword, not a shared meaning.

### 7c. Population minimum, decided and insufficient

An aggregate over a population must not become a way to read one person's
usage. The decision: **a single global floor**: below it, a group's NAME is
suppressed from any population output.

**Where it lives.** `cle/population/privacy.py`: `MIN_USERS = 3`, counted over
distinct users (one CLE instance is one user), with `MIN_GROUP = 3` (a group
must be big enough to describe at all) and a mechanical identifier screen that
judges a name on its raw form and on the form shown. `cle/population/reader.py`
refuses the same instance given twice, which would otherwise count one user as
two.

**Suppression, not a warning.** A warning leaves the name on screen and asks
the reader to disregard it, which is not a protection. Below the floor a group
keeps its id and its position on the plot and loses only its name.

**A single global floor is insufficient, and is known to be.** A rare agent
name can identify a team long before any global count is reached, and one floor
cannot express that. This is now observed rather than predicted: on WildChat two
groups were large enough to describe and came from two distinct people each, so
the floor suppressed both and the corpus names nothing at all. That is the floor
working - and equally the evidence that one number cannot express *how rare is
too rare*.

**The facet crosses §7b as a type, never as prose.** It is the one descriptive
text a topology carries, and it enters only as a validated `Facet`, only at
birth (`docs/CAPABILITIES.md` §12); `cause["facet"]` and a bare string are
refused with `FreeTextInTopologyError`, as `cause["reason"]` is.

Pinned by `tests/unit/test_population_privacy.py` and
`tests/unit/test_population_topology.py`, offline.
