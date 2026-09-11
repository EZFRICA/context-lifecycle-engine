"""topology.yaml writer - sole author of the topology file.

Contract (BLUEPRINT §7): every change is a commit in the same DAG under
the `topology/` ref prefix (one store, one audit trail). Entries carry
the evidence (or pre_evidence at birth) that caused them. `cle log
topology.yaml` renders the history with provenance and numbers; `cle
diff` renders the learned-topology delta. Diff size per version is a
deliverable measurement (logged on every write).

Version refs are `topology/v<n>`, n monotonically increasing; each
version object records its parent hash, so the chain is walkable without
trusting ref order.
"""

from cle.detect.embedders import EmbeddingConfig  # noqa: E402  (type + record)
from cle.lifecycle.reasons import (  # noqa: E402
    FreeTextInTopologyError,
    TopologyReason,
)
from cle.population.facet import Facet, FacetStatus  # noqa: E402


class FacetNotAtBirthError(ValueError):
    """A facet was supplied for an agent the topology already holds.

    Facet contract §c and §d-bis: a facet is generated once, at birth, and never
    again. Regenerating it would replace a record of the birth with today's model
    and today's prompt; back-generating one for an agent born before facets
    existed would present an artefact as a record of something it did not witness.
    """


class EmbeddingConfigMismatchError(Exception):
    """The topology inherited one vector space but is being written in another.

    Distinct from MissingEmbeddingConfigError on purpose: an ABSENT key and a
    LYING key are different failures. A key that lies is worse than one that is
    missing - a missing key excludes the history from an aggregate, a lying key
    puts it in the wrong bucket while looking accounted for.
    """


class MissingEmbeddingConfigError(Exception):
    """A topology write named no vector space and had no parent to inherit one.

    Loud on purpose: the embedding configuration is an AGGREGATION KEY, not
    metadata. A history missing it is comparable to no other history.
    """


import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from cle.oplog import OpLog
from cle.store.backends import StoreBackend
from cle.store.objects import content_hash


def _canonical(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def latest_version(backend: StoreBackend) -> tuple[int, dict | None]:
    refs = backend.list_refs("topology/v")
    if not refs:
        return 0, None
    number = max(int(name.split("/v")[1]) for name, _ in refs)
    target = dict(refs)[f"topology/v{number}"]
    return number, json.loads(backend.get(target))


def current_agents(backend: StoreBackend) -> dict[str, dict[str, Any]]:
    """The live agent index (name -> {state, image, since}) from the
    latest topology version - the lifecycle's source of truth."""
    _, latest = latest_version(backend)
    return dict(latest["agents"]) if latest else {}


def write_topology(
    *,
    backend: StoreBackend,
    path: Path,
    agent: str,
    state: str,
    image_hash: str,
    cause: dict[str, Any],
    oplog: OpLog,
    actor: str,
    on_behalf_of: str | None = None,
    embedding: "EmbeddingConfig | None" = None,
    reason: "TopologyReason | None" = None,
    facet: "Facet | None" = None,
    facet_status: "FacetStatus | None" = None,
) -> str:
    """Record one agent change as a new topology version + file rewrite.

    `cause` is the evidence/pre_evidence payload (with its kind) that
    justified the change - a topology entry without proof is exactly the
    prediction-driven drift the CLE exists to refuse.

    `facet` is level 2's input and the only prose a topology carries. It travels
    as its own typed parameter, the way `reason` and `embedding` do, and only at
    birth: a later write of the same agent carries the entry's facet forward
    untouched. `facet_status="generation_failed"` records a birth whose facet
    could not be produced; an entry with no status at all predates facets.
    """
    started = time.monotonic()
    # Decision (documented): downward moves may carry a bare human reason
    # - evidence justifies gains; losses need accountability, not proof.
    # STRUCTURAL BOUNDARY. A topology cause may carry proof, or a
    # closed-vocabulary reason - never prose. Callers pass `reason` as a typed
    # TopologyReason; stuffing a raw string into cause["reason"] is refused, so
    # the leak has no route rather than being sanitised on the way out.
    if "reason" in cause:
        raise FreeTextInTopologyError(
            "cause['reason'] is not a writable key: pass reason=TopologyReason(...) "
            "so the value is constrained to the closed vocabulary. Free user text "
            "belongs to the oplog note, which level 2 never reads."
        )
    if reason is not None:
        cause = {**cause, "reason": reason.reason}
    # Same boundary for the facet: prose enters only as a validated `Facet`.
    if "facet" in cause:
        raise FreeTextInTopologyError(
            "cause['facet'] is not a writable key: pass facet=Facet(...), built and "
            "validated by cle.population.facet"
        )
    if facet is not None and not isinstance(facet, Facet):
        raise FreeTextInTopologyError(
            f"facet must be a cle.population.facet.Facet, got {type(facet).__name__}; "
            "prose does not enter topology.yaml any other way"
        )
    if facet is None and facet_status == "present":
        raise ValueError("facet_status='present' was declared with no facet to store")

    if not cause or not any(
        k in cause for k in ("evidence", "pre_evidence", "persistence", "reason")
    ):
        raise ValueError("topology change requires an evidence-bearing cause (or a reason)")

    version_number, latest = latest_version(backend)
    agents = dict(latest["agents"]) if latest else {}
    previous_entry = agents.get(agent)
    if previous_entry is not None and (facet is not None or facet_status is not None):
        raise FacetNotAtBirthError(
            f"{agent!r} is already in the topology; its facet was settled at birth "
            "and is never regenerated or back-generated"
        )
    agents[agent] = {
        "state": state,
        "image": image_hash,
        "since": datetime.now(timezone.utc).isoformat(),
        "cause": cause,
    }
    if facet is not None:
        agents[agent]["facet"] = facet.model_dump()
        agents[agent]["facet_status"] = "present"
    elif facet_status is not None:
        agents[agent]["facet_status"] = facet_status
    elif previous_entry is not None:
        # A tag move rewrites the entry; the facet is data from the birth and
        # must survive every later write of the same agent.
        for key in ("facet", "facet_status"):
            if key in previous_entry:
                agents[agent][key] = previous_entry[key]
    # Embedding configuration is TOPOLOGY-scope, never per agent: it names the
    # vector space this whole history was produced in, and is therefore the key
    # any population-level aggregation must group by. Supplied at the first
    # write (the candidate birth, which knows the embedder) and INHERITED from
    # the parent record afterwards - a later tag move does not re-derive it.
    inherited = (latest or {}).get("embedding")
    declared = embedding.model_dump() if embedding is not None else None
    # A caller that DECLARES its vector space must agree with the one this
    # topology was born in. Inheritance without this check would let a config
    # change mid-life propagate the original silently, and the field would
    # assert something false - the one failure worse than having no key.
    if declared is not None and inherited is not None and declared != inherited:
        raise EmbeddingConfigMismatchError(
            f"topology was born under {inherited.get('embedder_id')!r} at threshold "
            f"{inherited.get('cluster_threshold')} but this write declares "
            f"{declared.get('embedder_id')!r} at {declared.get('cluster_threshold')}; "
            "a topology cannot change vector space in place - start a new history"
        )
    embedding_record = declared if declared is not None else inherited
    if embedding_record is None:
        # No silent fallback. A topology with no recorded vector space cannot be
        # compared with any other, and a report that aggregated it anyway would
        # measure its instrumentation instead of its population.
        raise MissingEmbeddingConfigError(
            "topology write has no embedding config and no parent to inherit one "
            "from; the first write must supply it (embedding_config_for(embedder))"
        )

    record = {
        "cle_kind": "topology",
        "version": version_number + 1,
        "embedding": embedding_record,
        "parent": (
            dict(backend.list_refs(f"topology/v{version_number}")).get(
                f"topology/v{version_number}"
            )
            if version_number
            else None
        ),
        "actor": actor,
        "agents": agents,
    }
    data = _canonical(record)
    record_hash = content_hash(data)
    backend.put(record_hash, data)
    backend.move_ref(f"topology/v{record['version']}", record_hash)

    # The visible artifact humans read; the store chain is the authority.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"version": record["version"], "embedding": embedding_record, "agents": agents},
            sort_keys=True, width=100
        )
    )
    # diff_size compares the durable half of the entry (state/image/cause);
    # `since` is a timestamp and would make every write look like a change.
    def _durable(entry: dict | None) -> dict | None:
        return {k: v for k, v in entry.items() if k != "since"} if entry else None

    diff_size = 1 if _durable(previous_entry) != _durable(agents[agent]) else 0
    oplog.emit(
        "topology_write",
        actor=actor,
        on_behalf_of=on_behalf_of,
        image=image_hash,
        to_state=state,
        diff_size=diff_size,
        version=record["version"],
        latency_ms=round((time.monotonic() - started) * 1000, 3),
        **{
            k: v
            for k, v in cause.items()
            if k in ("evidence", "pre_evidence", "persistence", "reason")
        },
    )
    return f"topology/v{record['version']}"


def render_log(backend: StoreBackend) -> str:
    """`cle log topology.yaml`: history with provenance and numbers."""
    lines = []
    for name, target in backend.list_refs("topology/v"):
        record = json.loads(backend.get(target))
        for agent, entry in sorted(record["agents"].items()):
            cause = entry.get("cause", {})
            proof_kind = next(
                (k for k in ("evidence", "pre_evidence", "persistence") if k in cause), "?"
            )
            numbers = cause.get(proof_kind, {})
            summary = ", ".join(f"{k}={v}" for k, v in list(numbers.items())[:3])
            lines.append(
                f"{name}  {agent}: {entry['state']}  image={entry['image'][:8]}  "
                f"by={record['actor']}  {proof_kind}({summary})"
            )
    return "\n".join(lines) if lines else "(no topology versions)"


def render_diff(backend: StoreBackend, ref_a: str, ref_b: str) -> str:
    """`cle diff`: the learned-topology delta between two versions."""
    versions = dict(backend.list_refs("topology/v"))
    for ref in (ref_a, ref_b):
        if ref not in versions:
            raise KeyError(f"unknown topology version {ref}")
    agents_a = json.loads(backend.get(versions[ref_a]))["agents"]
    agents_b = json.loads(backend.get(versions[ref_b]))["agents"]
    lines = []
    for agent in sorted(set(agents_a) | set(agents_b)):
        entry_a, entry_b = agents_a.get(agent), agents_b.get(agent)
        if entry_a == entry_b:
            continue
        if entry_a is None:
            lines.append(f"+ {agent}: {entry_b['state']} ({entry_b['image'][:8]})")
        elif entry_b is None:
            lines.append(f"- {agent}: was {entry_a['state']}")
        else:
            lines.append(
                f"~ {agent}: {entry_a['state']}@{entry_a['image'][:8]} -> "
                f"{entry_b['state']}@{entry_b['image'][:8]}"
            )
    return "\n".join(lines) if lines else "(no delta)"
