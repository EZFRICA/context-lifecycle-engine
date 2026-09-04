"""The closed vocabulary, and the boundary free text cannot cross.

SCOPE — 8 tests in bucket 1 (embedder-agnostic) and 2 in bucket 2
(stub-as-a-tool). Every assertion is about which VALUES may be written and
where; no vector space is involved. The two boundary tests that call
`write_topology` instantiate the stub only because a topology write requires an
embedding config — the stub is furniture, not the subject.

CLE need. `topology.yaml` is the single file level 2 reads. Free text in it is
two failures at once: unaggregatable (a population report can count descents but
never say WHY), and a content leak (a colleague's name reproduced in a
`cause.reason` on a descent to `archived` — the most-read path there is).

The requirement was a STRUCTURAL separation, not a sanitiser: a write-time
filter is bypassed by the next path someone adds. So the tests below assert a
TYPE property — that no representable route exists — plus an AST scrape that
fails when a new call site invents a value outside the vocabulary.

FALSE FRIEND, deliberately not constrained: `stability.py`'s `cluster_stability`
op also has a `reason=` kwarg. It is a technical diagnostic on a TECHNICAL op
(oplog.TECHNICAL_OPS), never reaches topology, and describes an instrument, not
a decision. Forcing it into the decision vocabulary would be renaming a
coincidence of keyword into a shared meaning.
"""

import ast
from pathlib import Path

import pytest
import yaml

from cle.lifecycle.reasons import (
    ALL_REASONS,
    ENGINE_AUTHORED,
    ENGINE_INFLUENCED,
    HUMAN_AUTHORED,
    FreeTextInTopologyError,
    TopologyReason,
    UnknownReasonError,
    classify_reason,
    validate_reason,
)

SOURCE_ROOT = Path(__file__).resolve().parent.parent.parent / "cle"

#: The one `reason=` kwarg in the package that is NOT a lifecycle decision.
TECHNICAL_REASON_SITES = {("detect/stability.py", "cluster_stability")}


# ── the type property: free text has no representable route ─────────────────

def test_a_reason_outside_the_vocabulary_cannot_be_constructed() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TopologyReason(reason="Marie du service RH trouve ça trop lent")


def test_the_r15_leak_is_refused_at_the_topology_boundary(tmp_path) -> None:
    # The exact value observed crossing into topology.yaml.
    import io

    from cle.detect.clusters import HashedTokenEmbedder
    from cle.detect.embedders import embedding_config_for
    from cle.lifecycle.topology import write_topology
    from cle.oplog import OpLog
    from cle.store.backends import InMemoryStore

    with pytest.raises(FreeTextInTopologyError):
        write_topology(
            backend=InMemoryStore(), path=tmp_path / "topology.yaml", agent="recap",
            state="archived", image_hash="0" * 64,
            cause={"reason": "Marie du service RH trouve ça trop lent"},
            oplog=OpLog(io.StringIO()), actor="human:t",
            embedding=embedding_config_for(HashedTokenEmbedder()),
        )


def test_the_written_record_carries_the_vocabulary_value_only(tmp_path) -> None:
    import io

    from cle.detect.clusters import HashedTokenEmbedder
    from cle.detect.embedders import embedding_config_for
    from cle.lifecycle.topology import write_topology
    from cle.oplog import OpLog
    from cle.store.backends import InMemoryStore

    write_topology(
        backend=InMemoryStore(), path=tmp_path / "topology.yaml", agent="recap",
        state="archived", image_hash="0" * 64, cause={},
        oplog=OpLog(io.StringIO()), actor="human:t",
        embedding=embedding_config_for(HashedTokenEmbedder()),
        reason=TopologyReason(reason="cost_regression"),
    )
    document = yaml.safe_load((tmp_path / "topology.yaml").read_text())
    assert document["agents"]["recap"]["cause"]["reason"] == "cost_regression"


# ── the two axes stay separated ─────────────────────────────────────────────

def test_engine_and_human_reasons_do_not_overlap() -> None:
    # A metric that fired and a person who judged must never aggregate as one
    # quantity — the same discipline as the three proof types.
    assert not (ENGINE_AUTHORED & HUMAN_AUTHORED)


def test_engine_influenced_is_human_but_isolable() -> None:
    # `engine_disagrees` is a human deferring to the engine. It must be
    # EXCLUDABLE, or a population aggregate would count the engine's own
    # influence as independent human judgement (Goodhart, at population scale).
    assert ENGINE_INFLUENCED <= HUMAN_AUTHORED
    assert ENGINE_INFLUENCED != HUMAN_AUTHORED


def test_every_reason_classifies_to_exactly_one_side() -> None:
    assert {classify_reason(r) for r in ALL_REASONS} == {"engine", "human"}


def test_an_unknown_reason_raises_rather_than_falling_into_a_catch_all() -> None:
    # No "other" bucket: it would silently absorb the whole distinction the
    # field exists to produce.
    with pytest.raises(UnknownReasonError):
        validate_reason("too_slow")


# ── the scrape: a new call site cannot invent a value ───────────────────────

#: What an f-string `reason=` reports as. An interpolated string is free text by
#: construction — it can never be a fixed vocabulary value — so it is reported
#: rather than skipped. Skipping it was the hole this constant closes: the one
#: pre-existing `reason=f"..."` (fingerprint drift, cli/main.py) would have
#: sailed past a scrape that only looked at plain literals.
INTERPOLATED = "<f-string>"


def _reason_kwarg_sites() -> list[tuple[str, str, str]]:
    """(relative path, enclosing op name, value) for every `reason=` passed a
    string literal or an f-string anywhere in the package."""
    found = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "reason":
                    continue
                if isinstance(keyword.value, ast.JoinedStr):
                    value = INTERPOLATED
                elif isinstance(keyword.value, ast.Constant) and isinstance(
                    keyword.value.value, str
                ):
                    value = keyword.value.value
                else:
                    continue  # a variable — covered by the runtime validation
                first_arg = node.args[0] if node.args else None
                op = (
                    first_arg.value
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str)
                    else ""
                )
                found.append((str(path.relative_to(SOURCE_ROOT)), op, value))
    return found


def test_every_literal_reason_in_the_package_is_in_the_vocabulary() -> None:
    offenders = [
        (path, op, value)
        for path, op, value in _reason_kwarg_sites()
        if (path, op) not in TECHNICAL_REASON_SITES and value not in ALL_REASONS
    ]
    assert not offenders, (
        f"free-text reason values at lifecycle call sites: {offenders}. "
        "Either use a value from cle/lifecycle/reasons.py, or add the new value "
        "there in the same change — never widen by writing prose."
    )


def test_the_scrape_actually_sees_something() -> None:
    # Guard against the scrape silently matching nothing and passing forever.
    assert _reason_kwarg_sites()


def test_the_technical_diagnostic_site_still_exists_as_declared() -> None:
    # If cluster_stability stops carrying `reason=`, this exemption is stale and
    # must be deleted rather than left to excuse some future call site.
    seen = {(path, op) for path, op, _ in _reason_kwarg_sites()}
    assert TECHNICAL_REASON_SITES <= seen, (
        "the declared technical exemption no longer matches any call site — "
        "remove it from TECHNICAL_REASON_SITES"
    )
