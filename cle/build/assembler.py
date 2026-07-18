"""Build stage 3 — assemble.

Contract (BLUEPRINT §3.3, §9 decision 3 as adopted in the approved P1
plan): compile the system prompt in declared order, capture
`model_fingerprint` (API version if exposed; else output hash over a fixed
probe set — 12 probes drawn from the cluster's replay window at build
time, frozen into the image), hash the complete artifact -> Image.
Invariant 1: image.hash != source.hash (structural via cle_kind).
Invariant 6: the fingerprint is what lets the re-validator expire proof.
"""

import json
from typing import Protocol, Sequence

import yaml

from cle.build.replay import ReplayOutcome
from cle.oplog import OpLog
from cle.store.backends import StoreBackend
from cle.store.commits import Image, PeriodSpec, SourceSpec, TriggerSpec
from cle.store.objects import Block, fetch_verified

# §9 decision 3: probe-set size, frozen into the image at build time.
PROBE_SET_SIZE = 12


class ModelFingerprinter(Protocol):
    """Produces the substrate identity an image was proven against.

    A live implementation hashes model outputs over the probe set (or the
    API version when exposed); P1's stub hashes deterministically so
    builds are reproducible offline. Same Protocol either way — the
    re-validator only ever compares fingerprints.
    """

    def fingerprint(self, probes: Sequence[str]) -> str: ...


class AssemblyError(Exception):
    """Stage-3 failure: the source declares no usable trigger or the
    resolved components cannot be compiled."""


def parse_trigger(source: SourceSpec) -> TriggerSpec:
    """Read the trigger the detector wrote into the candidate source.

    The centroid is produced by detect/ and only carried here — assembly
    never invents trigger geometry.
    """
    parsed = yaml.safe_load(source.yaml_raw)
    trigger_raw = parsed.get("trigger") if isinstance(parsed, dict) else None
    if not isinstance(trigger_raw, dict) or not isinstance(trigger_raw.get("centroid"), list):
        raise AssemblyError("source declares no trigger.centroid; the detector writes one")
    period_raw = trigger_raw.get("period")
    period = None
    if isinstance(period_raw, dict):
        period = PeriodSpec(
            interval=period_raw["interval"], tolerance=period_raw.get("tolerance", 0.25)
        )
    return TriggerSpec(centroid=tuple(float(v) for v in trigger_raw["centroid"]), period=period)


def assemble(
    *,
    source: SourceSpec,
    resolved_refs: dict[str, str],
    trigger: TriggerSpec,
    replay_outcome: ReplayOutcome,
    backend: StoreBackend,
    fingerprinter: ModelFingerprinter,
    oplog: OpLog,
) -> Image:
    """Compile the prompt in declared order and freeze the artifact.

    Declared order = the order of `components` in the source (which is
    the iteration order of resolved_refs, preserved since resolve walks
    the list). Probes: the first PROBE_SET_SIZE in-cluster openers of the
    replay window, chronological — deterministic, no sampling."""
    fragments: list[str] = []
    for ref, target_hash in resolved_refs.items():
        payload = fetch_verified(backend, target_hash, oplog)
        record = json.loads(payload)
        if record.get("cle_kind") != "block":
            raise AssemblyError(f"component {ref} is not a block")
        fragments.append(Block(kind=record["kind"], payload=record["payload"]).payload)

    probes = replay_outcome.in_cluster_openers[:PROBE_SET_SIZE]
    return Image(
        source_hash=source.hash,
        resolved_refs=resolved_refs,
        assembled_prompt="\n\n".join(fragments),
        trigger=trigger,
        model_fingerprint=fingerprinter.fingerprint(probes),
        pre_evidence=replay_outcome.pre_evidence,
        probe_set=probes,
    )
