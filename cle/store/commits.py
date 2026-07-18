"""SourceSpec, Image, evidence types, and tag-target rules.

Contract (cle-core-contracts, BLUEPRINT §4-§5):
- `SourceSpec(yaml_raw, hash)` — the candidate's source, hashed as-is.
- `Image(source_hash, resolved_refs, assembled_prompt, trigger,
  model_fingerprint, pre_evidence, hash)` — the built artifact; `hash`
  covers ALL fields. Invariant 1: image.hash != source.hash, always
  (structural via cle_kind domain separation, see Storable).
- Lifecycle tags attach to Image hashes only; tagging anything else raises
  `TagTargetError` — `assert_tag_target` is the single guard every tagging
  path must route through.
- Three evidence types, distinct at type level (invariant 5):
  `PreEvidence` (replay, retrospective) / `Evidence` (trial, lived) /
  `Persistence` (re-validation, drift). A function expecting Evidence
  rejects PreEvidence.
"""

import json
from datetime import timedelta
from typing import ClassVar

from pydantic import BaseModel, Field

from cle.oplog import OpLog
from cle.store.backends import StoreBackend
from cle.store.objects import Storable, fetch_verified


class PeriodSpec(BaseModel, frozen=True):
    """Temporal half of a trigger, for recurrence-born agents.

    CLE need (BLUEPRINT §4): a recurrence agent fires on schedule, so its
    trigger must record the observed period and how much jitter the lived
    history showed.
    """

    interval: timedelta
    tolerance: float = Field(ge=0.0)


class TriggerSpec(BaseModel, frozen=True):
    """ENTRYPOINT of an image — immutable, in-image (BLUEPRINT §4).

    centroid is produced by detect/ and tested by replay; period is the
    optional temporal condition for recurrence agents.
    """

    centroid: tuple[float, ...]
    period: PeriodSpec | None = None


class PreEvidence(BaseModel, frozen=True):
    """Replay output — retrospective, zero risk; gates the BUILD only.

    CLE need (BLUEPRINT §5): cold-start proof. Replay validates the
    trigger, never answer quality, so these numbers may never justify a
    promotion — hence a type with no lineage to Evidence.
    """

    capture_rate: float = Field(ge=0.0, le=1.0)
    false_trigger_rate: float = Field(ge=0.0, le=1.0)
    # Mean iteration cost of the cluster under the current topology — the
    # numeric justification of the birth.
    historical_cost: float = Field(ge=0.0)
    # The replay window as requested (e.g. "30d"); the replay report ties
    # it to absolute bounds at run time.
    window: str


class Evidence(BaseModel, frozen=True):
    """Trial output — lived value on natural occurrences; gates promotion.

    Mandatory on every upward tag move (invariant 4).
    """

    # Trial cost relative to the cluster's historical cost; <1 means the
    # agent earns its keep.
    cost_ratio: float = Field(gt=0.0)
    occurrences: int = Field(ge=1)
    closure_tags: tuple[str, ...]


class Persistence(BaseModel, frozen=True):
    """Re-validation output — proof expiry on substrate drift (invariant 6)."""

    fingerprint_at_build: str
    fingerprint_now: str
    # Ids of frozen probes whose outputs changed under the served model;
    # non-empty deltas are what trigger auto-demotion to trial.
    probe_deltas: tuple[str, ...]


class SourceSpec(Storable, frozen=True):
    """The candidate's YAML source, exactly as detected/authored.

    yaml_raw is embedded verbatim in the canonical record — no
    parse-then-normalize — so the source hash names what the human or
    detector actually wrote and a byte-level change is a new candidate
    identity.
    """

    _cle_kind: ClassVar[str] = "source_spec"

    yaml_raw: str


class Image(Storable, frozen=True):
    """The built artifact — the only thing lifecycle tags may point at.

    Contract fields per cle-core-contracts / BLUEPRINT §4; `hash` (the
    Storable property) covers ALL fields via the canonical encoding.
    `probe_set` carries §9 decision 3: the probes drawn from the cluster's
    replay window at build time, frozen in-image so the re-validator can
    replay the exact same set against a drifted model (invariant 6).
    """

    _cle_kind: ClassVar[str] = "image"

    source_hash: str
    resolved_refs: dict[str, str]
    assembled_prompt: str
    trigger: TriggerSpec
    model_fingerprint: str
    pre_evidence: PreEvidence
    probe_set: tuple[str, ...]


class TagTargetError(Exception):
    """Lifecycle tags attach to Image hashes only (invariant 1)."""


def assert_tag_target(backend: StoreBackend, target_hash: str, oplog: OpLog) -> None:
    """Verify a hash addresses an image before any tag may touch it.

    Fetches the record (integrity-checked) and inspects its cle_kind
    domain marker — a hash alone cannot be inverted, so the store record
    is the authority on what kind of thing it names. Every tagging path
    (P3 `cle tag`, the shadow engine) must call this before move_ref.
    """
    try:
        record = json.loads(fetch_verified(backend, target_hash, oplog))
    except json.JSONDecodeError:
        raise TagTargetError(
            f"tags attach to image hashes only; {target_hash[:8]} is not a canonical record"
        ) from None
    record_kind = record.get("cle_kind") if isinstance(record, dict) else None
    if record_kind != "image":
        raise TagTargetError(
            f"tags attach to image hashes only; {target_hash[:8]} is {record_kind or 'unknown'}"
        )
