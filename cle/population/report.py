"""The population report: counts, screened names, and never a facet's text.

`discover` runs stages 2 to 4 over what `reader.read_population` collected. Its
output is what may leave the engine, so it is built to carry nothing that could
be joined back to one person: group sizes and user counts, a name only where the
floor and the screen allow one, and the instance ids nowhere at all.
"""

from pathlib import Path
from typing import Sequence

from pydantic import BaseModel

from cle.detect.clusters import Embedder
from cle.population.grouping import LEVEL2_LOOSER, build_hierarchy, embed_all, group
from cle.population.naming import Namer, name_groups
from cle.population.privacy import MIN_GROUP, MIN_USERS
from cle.population.reader import PopulationEntry, PopulationError


class GroupSummary(BaseModel, frozen=True):
    group: int
    size: int
    users: int
    #: `None` below the user floor, or when the screen refused the name.
    name: str | None
    family: int


class PopulationReport(BaseModel, frozen=True):
    embedder_id: str
    threshold: float
    family_threshold: float
    namer_id: str
    min_users: int
    min_group: int
    instances: int
    agents: int
    without_facet: dict[str, int]
    groups: int
    named: int
    singletons: int
    below_user_floor: int
    refused_names: int
    families: int
    largest_families: list[int]
    sizes: list[int]
    group_summaries: list[GroupSummary]


def write_report(report: PopulationReport, out: Path) -> Path:
    """Write `report.json` under `out`, and nowhere else.

    A population run writes only here: never into the instances it read.
    """
    out.mkdir(parents=True, exist_ok=True)
    target = out / "report.json"
    target.write_text(report.model_dump_json(indent=2))
    return target


def discover(entries: Sequence[PopulationEntry], *, embedder: Embedder, namer: Namer,
             threshold: float, instances: int, without_facet: dict[str, int],
             looser: float = LEVEL2_LOOSER) -> PopulationReport:
    embedder_id = getattr(embedder, "embedder_id", None)
    if not embedder_id:
        raise PopulationError(
            "the population embedder names no vector space; a report whose groups "
            "cannot say which space they were formed in is comparable to nothing"
        )
    family_threshold = round(max(0.0, threshold - looser), 3)
    texts = [e.facet for e in entries]
    space = embed_all(texts, embedder)
    ids = group(texts, space, threshold) if texts else []

    members: dict[int, list[str]] = {}
    users: dict[int, set[str]] = {}
    for gid, entry in zip(ids, entries):
        members.setdefault(gid, []).append(entry.facet)
        users.setdefault(gid, set()).add(entry.instance)
    naming = name_groups(members, users, namer)
    parents, families = build_hierarchy(ids, texts, space, threshold, looser) if texts else ([], {})
    parent_of = dict(zip(ids, parents))

    sizes = sorted((len(m) for m in members.values()), reverse=True)
    return PopulationReport(
        embedder_id=embedder_id,
        threshold=threshold,
        family_threshold=family_threshold,
        namer_id=namer.namer_id,
        min_users=MIN_USERS,
        min_group=MIN_GROUP,
        instances=instances,
        agents=len(entries),
        without_facet=dict(without_facet),
        groups=len(members),
        named=len(naming.names),
        singletons=sum(1 for s in sizes if s == 1),
        below_user_floor=naming.below_user_floor,
        refused_names=naming.refused,
        families=len(families),
        largest_families=sorted((len(v) for v in families.values()), reverse=True)[:8],
        sizes=sizes[:20],
        group_summaries=[
            GroupSummary(group=gid, size=len(members[gid]), users=len(users[gid]),
                         name=naming.names.get(gid), family=parent_of[gid])
            for gid in sorted(members)
        ],
    )
