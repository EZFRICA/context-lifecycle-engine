"""Two READ views over the one write path — classification + provenance.

SCOPE — bucket 1 (embedder-agnostic): no embedder is involved anywhere here;
these assertions hold in any era and any vector space.

Invariant 4 is what these guard indirectly: there is still exactly ONE writer
(`OpLog.emit`). Splitting technical from decision is a read concern, so the
risk is not duplication — it is an op that nobody classified silently vanishing
from the audit view. That is what `test_every_emitted_op_classifies` exists to
catch, by scraping the ops the CODE actually emits rather than a hand-kept list.
"""

import ast
import pathlib

import pytest

from cle.oplog import (
    DECISION_OPS,
    TECHNICAL_OPS,
    UnclassifiedOpError,
    classify_op,
    render_decision,
    requires_on_behalf_of,
)

CLE_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent / "cle"


def _ops_emitted_by_the_code() -> set[str]:
    """Every literal op name passed to `OpLog.emit` anywhere in cle/.

    Parsed from the AST, not grepped, so a multi-line call is seen and a
    commented-out one is not. A dynamic op name (there are none today) would
    be invisible here — that is a known limit of this scrape, not a silent
    pass: it would surface as an unclassified op at runtime instead.
    """
    found: set[str] = set()
    for path in CLE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "emit"):
                continue
            for arg in node.args[:1]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.add(arg.value)
                elif isinstance(arg, ast.IfExp):  # `"a" if cond else "b"`
                    for branch in (arg.body, arg.orelse):
                        if isinstance(branch, ast.Constant):
                            found.add(branch.value)
    return found


def test_every_emitted_op_classifies_into_exactly_one_bucket() -> None:
    emitted = _ops_emitted_by_the_code()
    assert emitted, "found no emit() call sites — the AST scrape is broken"
    unclassified = [op for op in sorted(emitted) if op not in TECHNICAL_OPS | DECISION_OPS]
    assert not unclassified, (
        f"ops emitted but classified nowhere: {unclassified}. Classify them in "
        "cle/oplog.py in the same change that emits them."
    )
    both = sorted(TECHNICAL_OPS & DECISION_OPS)
    assert not both, f"ops in BOTH buckets: {both}"
    for op in sorted(emitted):
        assert classify_op(op) in ("technical", "decision")


def test_an_unknown_op_raises_rather_than_defaulting() -> None:
    # Defaulting to "technical" would drop a new decision from the audit view
    # without anyone noticing. Loud beats silent.
    with pytest.raises(UnclassifiedOpError):
        classify_op("some_future_op")


def test_the_two_buckets_are_disjoint_and_non_empty() -> None:
    assert TECHNICAL_OPS and DECISION_OPS
    assert TECHNICAL_OPS.isdisjoint(DECISION_OPS)


# ── on_behalf_of (2b) ───────────────────────────────────────────────────────

def test_decision_ops_naming_a_subject_require_on_behalf_of() -> None:
    tied = {"op": "tag", "actor": "human:x", "image": "abc12345", "to": "candidate"}
    assert requires_on_behalf_of(tied)


def test_technical_ops_never_require_on_behalf_of() -> None:
    # "For whom did this happen" is meaningless for a mechanical step; run and
    # switch already carry `workspace`, which IS their on-behalf-of (aliased,
    # never duplicated).
    for op in sorted(TECHNICAL_OPS):
        record = {"op": op, "actor": "system:x", "image": "abc12345", "workspace": "alpha"}
        assert not requires_on_behalf_of(record), op


def test_a_decision_op_naming_nobody_requires_nothing() -> None:
    assert not requires_on_behalf_of({"op": "topology_write", "actor": "human:x"})


# ── the audit sentence ──────────────────────────────────────────────────────

def test_shadow_lines_are_never_rendered_as_a_move() -> None:
    # The shadow engine emits a `tag` op that writes no ref. Rendering it as a
    # move would put a decision in the audit trail that never happened.
    shadow = {"op": "tag", "actor": "engine:shadow", "image": "abc12345",
              "from": "trial", "would": "ephemeral",
              "evidence": {"occurrences": 4, "cost_ratio": 0.6}}
    sentence = render_decision(shadow)
    assert "would: ephemeral" in sentence and "no ref written" in sentence
    assert "moved" not in sentence


def test_the_sentence_carries_actor_subject_and_on_behalf_of() -> None:
    record = {"op": "tag", "actor": "human:ada", "on_behalf_of": "u1",
              "image": "abc12345", "to": "candidate",
              "pre_evidence": {"capture_rate": 1.0, "false_trigger_rate": 0.08}}
    sentence = render_decision(record)
    assert "human:ada" in sentence
    assert "on behalf of u1" in sentence
    assert "abc12345" in sentence
    assert "capture" in sentence


def test_the_birth_path_actually_emits_on_behalf_of() -> None:
    """Not just that the rule says it is required — that the code writes it.

    Exercises the real `move_state_tag` used at candidate birth and reads the line
    back off the sink.
    """
    import io
    import json as _json

    from cle.lifecycle.tags import move_state_tag
    from cle.oplog import OpLog
    from cle.store.backends import InMemoryStore
    from cle.store.commits import Image, PreEvidence, TriggerSpec

    pre = PreEvidence(capture_rate=1.0, false_trigger_rate=0.0,
                      historical_cost=3.0, window="30d")
    image = Image(
        source_hash="0" * 64, resolved_refs={}, assembled_prompt="p",
        trigger=TriggerSpec(centroid=(1.0, 0.0), embedder_id="stub:hashed64"),
        model_fingerprint="f" * 64, pre_evidence=pre,
        probe_set=("probe",), probe_output_hashes=("h",),
    )
    store = InMemoryStore()
    store.put(image.hash, image.canonical_bytes())
    image_hash = image.hash
    sink = io.StringIO()
    move_state_tag(
        backend=store, agent="weekly_recap", image_hash=image_hash, from_state=None,
        to_state="candidate",
        pre_evidence=pre,
        oplog=OpLog(sink), actor="human:test", on_behalf_of="u1",
    )
    record = _json.loads(sink.getvalue().strip())
    assert requires_on_behalf_of(record), "a birth names a subject, so it must carry provenance"
    assert record["on_behalf_of"] == "u1"
