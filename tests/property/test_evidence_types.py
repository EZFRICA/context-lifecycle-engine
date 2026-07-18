"""Invariant 5 / BLUEPRINT §5 — three standards of proof, three types.

Mandated test 5 of cle-core-contracts (test_pre_evidence_not_evidence),
written before the types exist. Replay output (PreEvidence) must be
rejected by every promotion path at type level; the runtime gate is
require_evidence, which all upward tag moves route through.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from cle.lifecycle.tags import require_evidence
from cle.store.commits import Evidence, Persistence, PreEvidence

rates = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


def _pre_evidence(capture_rate: float = 0.9) -> PreEvidence:
    return PreEvidence(
        capture_rate=capture_rate,
        false_trigger_rate=0.01,
        historical_cost=4.2,
        window="30d",
    )


def test_the_three_types_share_no_lineage() -> None:
    # No subclassing between the standards of proof, in any direction —
    # substitutability is exactly what invariant 5 forbids.
    for weaker, stronger in [
        (PreEvidence, Evidence),
        (Evidence, PreEvidence),
        (Persistence, Evidence),
        (Evidence, Persistence),
        (PreEvidence, Persistence),
        (Persistence, PreEvidence),
    ]:
        assert not issubclass(weaker, stronger)


@given(capture_rate=rates)
def test_pre_evidence_not_evidence(capture_rate: float) -> None:
    # However good the replay numbers, they are retrospective — the
    # promotion gate rejects them regardless of magnitude.
    with pytest.raises(TypeError):
        require_evidence(_pre_evidence(capture_rate))


def test_persistence_is_not_evidence_either() -> None:
    persistence = Persistence(
        fingerprint_at_build="fp-a",
        fingerprint_now="fp-b",
        probe_deltas=("probe-3",),
    )
    with pytest.raises(TypeError):
        require_evidence(persistence)


def test_lived_evidence_passes_the_gate() -> None:
    evidence = Evidence(cost_ratio=0.4, occurrences=7, closure_tags=("success", "success"))
    assert require_evidence(evidence) is evidence


def test_evidence_subclass_is_rejected() -> None:
    # The gate is exact-type: an Evidence face is not Evidence. A subclass
    # built from replay numbers is the smuggling path this closes.
    class SmuggledEvidence(Evidence, frozen=True):
        pass

    smuggled = SmuggledEvidence(cost_ratio=0.4, occurrences=7, closure_tags=())
    with pytest.raises(TypeError):
        require_evidence(smuggled)


def test_evidence_types_are_frozen() -> None:
    evidence = Evidence(cost_ratio=0.4, occurrences=7, closure_tags=())
    with pytest.raises(ValidationError):
        evidence.cost_ratio = 0.1  # type: ignore[misc]
