"""Level 2 over the three bench corpora: the engine's stages, BigQuery's vectors.

The grouping, the user floor, the name screen and the hierarchy are the
engine's (`cle.population`). This script adds only what the engine does not do
offline: the bench vector space `bigquery:gemini-embedding-001:768`, in which
the facets of Stack Overflow, WildChat and GDG were embedded, and a namer that
runs on BigQuery. Everything the board shows about groups therefore comes from
the same code `cle population` runs.

Only the GDG corpus carries intents, because they were planted there. Stack
Overflow and WildChat have none - real usage does not arrive labelled.

**A DISCOVERED INTENT IS NOT A LABEL, and the board must never show it as one.**
The planted intents in GDG are ground truth. A discovered name is the system's
own hypothesis about what a group has in common; scoring a method against labels
it produced itself would be circular, which is why nothing here feeds the recall
tables.

THE THRESHOLD IS A PARAMETER. 0.78 is where the planted GDG intents grouped best:

    threshold  groups  purity  completeness      F
         0.70       3     54%          100%  0.704
         0.75       5     61%           89%  0.723
         0.78       9     76%           80%  0.782   <- default
         0.85      23     91%           52%  0.664
         0.94      45     98%           15%  0.263

Purity alone would be a trap: 45 groups for 46 clusters is 98% pure and says
nothing. Completeness - does one intent stay in one group - is what
over-splitting destroys, so the balance of the two chooses. On another corpus the
right value differs, and the share of singletons with it; pass another value as
the first argument.

BILLS: one embedding per distinct facet, one generation per nameable group.
"""
import json
import pathlib
import sys
import time
from typing import Mapping, Sequence

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "examples" / "bigquery"))
sys.path.insert(0, str(ROOT))

from cle.population.grouping import LEVEL2_LOOSER, Precomputed, build_hierarchy, group  # noqa: E402
from cle.population.naming import MAX_PROMPT_MEMBERS, NAME_PROMPT, name_groups  # noqa: E402
from cle.population.privacy import MIN_GROUP, MIN_USERS  # noqa: E402

BENCH_SPACE = "bigquery:gemini-embedding-001:768"
VIEWS = ("so_view", "real_view", "crossuser_view")


class BigQueryNamer:
    """Raw group names from `ML.GENERATE_TEXT`, at temperature 0, in one batch.

    Returns RAW names. The floor, the cleaning and the identifier screen are
    `cle.population.naming.name_groups`, which is the only path to a shown name.
    """

    namer_id = "bigquery:gen_gemini_flash:name-prompt-v1"

    def name(self, groups: Mapping[int, Sequence[str]]) -> dict[int, str]:
        import pandas as pd
        from google.cloud import bigquery

        import bqconfig

        client = bigquery.Client(project=bqconfig.project())
        P = bqconfig.dataset()
        frame = pd.DataFrame({
            "gid": [str(g) for g in groups],
            "prompt": [NAME_PROMPT.format(
                members="\n".join(f"- {x}" for x in list(m)[:MAX_PROMPT_MEMBERS]))
                for m in groups.values()],
        })
        client.load_table_from_dataframe(
            frame, f"{P}.r28_group_prompts",
            job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
        ).result()
        t0 = time.perf_counter()
        client.query(f"""
        CREATE OR REPLACE TABLE `{P}.r28_group_names` AS
        SELECT gid, ml_generate_text_llm_result AS name
        FROM ML.GENERATE_TEXT(
          MODEL `{P}.gen_gemini_flash`,
          (SELECT gid, prompt FROM `{P}.r28_group_prompts`),
          STRUCT(0.0 AS temperature, 12 AS max_output_tokens, TRUE AS flatten_json_output))
        """, location="EU").result()
        print(f"    named {len(groups)} groups in {time.perf_counter() - t0:.0f}s")
        return {int(r["gid"]): r["name"] or "" for r in client.query(
            f"SELECT gid, name FROM `{P}.r28_group_names`", location="EU").result()}


def discover(view_path: pathlib.Path, threshold: float) -> dict:
    """Group and name one corpus's facets, writing the result back into its view."""
    view = json.loads(view_path.read_text(encoding="utf-8"))
    points = view["views"]["facet"]["points"]
    facets = [p["facet"] for p in points]

    # The view holds projected coordinates, not the 768 dimensions the grouping
    # needs, so the vectors are recomputed rather than approximated from the plot.
    from facet_crossuser_bench import embed

    space = Precomputed({k: tuple(v) for k, v in embed(sorted(set(facets))).items()}, BENCH_SPACE)
    ids = group(facets, space, threshold)

    members: dict[int, list[str]] = {}
    users: dict[int, set[str]] = {}
    for gid, facet, point in zip(ids, facets, points):
        members.setdefault(gid, []).append(facet)
        users.setdefault(gid, set()).add(point.get("user", ""))
    naming = name_groups(members, users, BigQueryNamer())
    if naming.refused:
        print(f"    {naming.refused} name(s) refused by the identifier screen")
    names = naming.names

    parents, families = build_hierarchy(ids, facets, space, threshold)
    # A family is named after its largest named child, so the second level reads
    # in the same vocabulary as the first instead of inventing another.
    family_name: dict[int, str] = {}
    for pid, children in families.items():
        labelled = [(len(members[c]), names[c]) for c in children if c in names]
        if labelled:
            family_name[pid] = max(labelled)[1]

    for view_name in view["views"]:
        for point, gid, pid in zip(view["views"][view_name]["points"], ids, parents):
            point["group"] = gid
            point["discovered"] = names.get(gid, "")
            point["family"] = pid
            point["family_name"] = family_name.get(pid, "")

    sizes = sorted((len(m) for m in members.values()), reverse=True)
    view["discovery"] = {
        "threshold": threshold,
        "space": BENCH_SPACE,
        "groups": len(members),
        "named": len(names),
        "min_group": MIN_GROUP,
        "min_users": MIN_USERS,
        "below_user_floor": naming.below_user_floor,
        "users_per_named": {names[g]: len(users[g]) for g in names},
        "families": len(families),
        "family_threshold": round(max(0.0, threshold - LEVEL2_LOOSER), 3),
        "largest_families": sorted((len(v) for v in families.values()), reverse=True)[:8],
        "sizes": sizes[:20],
        "singletons": sum(1 for s in sizes if s == 1),
    }
    view_path.write_text(json.dumps(view, ensure_ascii=False), encoding="utf-8")
    return view["discovery"]


def check_against_gdg(view_path: pathlib.Path) -> None:
    """Grade discovery where the answer is known: purity against planted intents."""
    view = json.loads(view_path.read_text(encoding="utf-8"))
    points = view["views"]["facet"]["points"]
    if not points or not points[0].get("intent"):
        return
    by_group: dict[int, list[str]] = {}
    for p in points:
        by_group.setdefault(p["group"], []).append(p["intent"])
    correct = sum(intents.count(max(set(intents), key=intents.count))
                  for intents in by_group.values())
    print(f"    purity against the planted intents: {correct}/{len(points)} "
          f"({correct / len(points):.0%}) over {len(by_group)} groups (7 were planted)")


def main() -> None:
    """Usage: discover_intents.py [threshold] [view ...]

    Naming bills a generation call per group, so a view can be named on its own
    rather than re-running all three to repair one.
    """
    args = sys.argv[1:]
    threshold = 0.78
    if args and args[0].replace(".", "", 1).isdigit():
        threshold = float(args.pop(0))
    unknown = [a for a in args if a not in VIEWS]
    if unknown:
        raise SystemExit(f"unknown view(s) {unknown}; known: {list(VIEWS)}")
    for name in (tuple(args) or VIEWS):
        path = HERE / "data" / f"{name}.json"
        if not path.exists():
            print(f"  {name}: absent, skipped")
            continue
        print(f"  {name}:")
        summary = discover(path, threshold)
        print(f"    {summary['groups']} groups, {summary['named']} named, "
              f"{summary['singletons']} singletons, largest {summary['sizes'][:5]}")
        print(f"    {summary['families']} families at threshold "
              f"{summary['family_threshold']}, largest {summary['largest_families'][:5]}")
        if summary["below_user_floor"]:
            print(f"    {summary['below_user_floor']} group(s) big enough to name but "
                  f"under {summary['min_users']} distinct users - left unnamed")
        check_against_gdg(path)


if __name__ == "__main__":
    sys.exit(main())
