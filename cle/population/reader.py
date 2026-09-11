"""The only way into level 2: `topology.yaml` records, and nothing else.

BLUEPRINT §7b names `topology.yaml` as the only file a population level reads.
This module is that reading. It opens each instance's store, takes the LATEST
topology version, and collects the facets its agents carry - never the store's
images, never the oplog, never a message.

Three refusals, each protecting what the report would otherwise claim:

  * a directory with no topology is an operator error, not an empty user;
  * two instances born in different vector spaces cannot be aggregated -
    BLUEPRINT §7: a report that did would measure its own instrumentation;
  * the same instance given twice would count one user as two, which is exactly
    how a k-anonymity floor is bypassed.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from cle.lifecycle.topology import latest_version
from cle.population.facet import facet_from_record
from cle.store.backends import StoreBackend, open_store, store_exists


class PopulationError(Exception):
    """The inputs cannot form one population."""


class MixedSpaceError(PopulationError):
    """Two topologies were born under different embedding configurations."""


@dataclass(frozen=True)
class PopulationEntry:
    #: An anonymous, stable id for one CLE instance - one user.
    instance: str
    agent: str
    facet: str


@dataclass(frozen=True)
class PopulationInput:
    entries: list[PopulationEntry]
    #: The level-1 embedding key every instance shares.
    embedding: dict[str, object]
    instances: int
    #: Agents without a facet, split by WHY (contract §d-bis).
    without_facet: dict[str, int] = field(default_factory=dict)


def instance_id(backend: StoreBackend) -> str:
    """The content hash of the instance's FIRST topology version, truncated.

    Stable for the life of the instance, different between instances, and
    carrying nothing about where the instance lives: a path would name a user.
    """
    return dict(backend.list_refs("topology/v1"))["topology/v1"][:12]


def read_population(state_dirs: Sequence[Path]) -> PopulationInput:
    entries: list[PopulationEntry] = []
    without = {"predates_facets": 0, "generation_failed": 0}
    key: dict[str, object] | None = None
    seen: set[str] = set()
    for state_dir in state_dirs:
        # Asked before opening: opening creates the store, and a population run
        # never writes into an instance it reads - not even an empty directory.
        backend = open_store(state_dir) if store_exists(state_dir) else None
        record = latest_version(backend)[1] if backend is not None else None
        if backend is None or record is None:
            raise PopulationError(f"{state_dir} holds no topology; nothing was ever born there")
        embedding = record.get("embedding") or {}
        this_key = {k: embedding.get(k) for k in ("embedder_id", "cluster_threshold")}
        if key is None:
            key = this_key
        elif this_key != key:
            raise MixedSpaceError(
                f"{state_dir} was born under {this_key} but the population so far "
                f"under {key}; aggregating them would compare centroids from two "
                "detection configurations and measure the instruments, not the users"
            )
        instance = instance_id(backend)
        if instance in seen:
            raise PopulationError(
                f"{state_dir} is an instance already given; counting it twice would "
                "count one user as two and let a name through the user floor"
            )
        seen.add(instance)
        for agent, entry in sorted(record["agents"].items()):
            status = entry.get("facet_status")
            if status == "present":
                facet = facet_from_record(entry["facet"])
                entries.append(PopulationEntry(instance=instance, agent=agent, facet=facet.text))
            elif status == "generation_failed":
                without["generation_failed"] += 1
            else:
                without["predates_facets"] += 1
    return PopulationInput(entries=entries, embedding=dict(key or {}),
                           instances=len(seen), without_facet=without)
