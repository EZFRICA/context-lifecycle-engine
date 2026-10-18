## Level 2: the population layer

Level 2 is in the engine, in its own package, `cle/population/`. Every true
birth writes a **facet** - one sentence describing what the agent does - into
its topology entry, and `cle population` reads the topologies of many instances,
one per user, and groups their agents by what they do (Clio's four stages):

```bash
uv run cle population .cle-user-a .cle-user-b .cle-user-c --out .cle-population
```

It reads `topology.yaml` records and nothing else, and writes `report.json` and
one op line under `--out`. A group is named only when at least 3 members come
from at least 3 distinct users, and a name carrying a proper noun or a long
number is refused rather than shown; below the floor a group keeps its id and
its size and loses only its name. The report never quotes a facet. `--threshold`
is a parameter: the right value depends on the corpus. See
`docs/CAPABILITIES.md` §12.

**Live, on three models.** Three users born on a live model, then grouped by it:

```bash
CLE_FORCE_REAL_MODEL=1 uv run python examples/run_multiuser.py \
  --state-root /tmp/l2 --embedder cached --model-id gemini-3.8-flash
GEMINI_MODEL=gemini-3.8-flash uv run cle --embedder real population \
  /tmp/l2/user1 /tmp/l2/user2 /tmp/l2/user3 --namer live --out /tmp/l2-pop
```

Measured 2026-09-10, one run per model, in `google:gemini-embedding-2:768` at
its calibrated 0.775 (no `--threshold`, so the space's value applies):

| | `gemini-3.5-flash-lite` | `gemini-3.6-flash` | `gemini-3.8-flash` |
|---|---|---|---|
| facets written at birth | 3 of 3 `present` | 3 of 3 `present` | 3 of 3 `present` |
| groups (sizes) | 2 (2, 1) | 2 (2, 1) | 2 (2, 1) |
| the pair grouped | events + venue (0.884) | **events + newsletter** (0.787) | events + venue (0.810) |
| families at 0.735 | 2 | 2 | **1** |
| named | 0 | 0 | 0 |
| facets quoted in the report | 0 | 0 | 0 |

The sizes agree on all three models; the members do not. Under
`gemini-3.6-flash` the events facet reads closer to the newsletter one than to
the venue one, so the pair changes while every count stays the same: a report
of sizes alone cannot show a change of model. Under `gemini-3.8-flash` the
singleton joins the pair one level up. Nothing is named on any model, because
three users is the floor itself and no group reaches it. The runs exercise the
path, not a population, and one run per model cannot separate the model from its
sampling.
