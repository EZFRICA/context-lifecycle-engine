"""GDG fixture structural sanity + label targeting (sidecar-driven).

Realism run: the fixture is 16 weeks of varied usage grouped by PLANTED
intent (thread prefix). Domain/tool checks and label counts read the sidecar;
nothing here assumes the detector recovers clean clusters (it does not).
"""

import pytest

DOMAIN_TOOL = {"events": "calendar_api", "speakers": "outreach_email",
               "sponsors": "sponsor_crm"}


def test_scale(gdg) -> None:
    assert len(gdg.episodes) >= 200
    span = (gdg.messages[-1].ts - gdg.messages[0].ts).days
    assert 105 <= span <= 112  # 16 weeks


@pytest.mark.parametrize("intent,tool", list(DOMAIN_TOOL.items()))
def test_planted_domain_carries_its_tool(gdg, intent, tool) -> None:
    # Every episode of a tool-bearing planted intent declares that tool
    # (declaration only — nothing executed).
    assert all(e.required_tool == tool for e in gdg.planted(intent))


def test_community_episodes_carry_no_tool(gdg) -> None:
    toolless = [e for e in gdg.episodes if e.required_tool is None]
    assert len(toolless) > 80  # Q&A + noise dominate the tool-less side


@pytest.mark.parametrize("conflict_type,minimum",
                         [("intra_cluster", 2), ("temporal", 2), ("routing", 2), ("world_state", 2)])
def test_all_four_conflict_types_are_planted(gdg, conflict_type, minimum) -> None:
    labeled = [t for t, v in gdg.ground["labeled_threads"].items() if v == conflict_type]
    assert len(labeled) >= minimum


def test_labels_live_only_in_the_sidecar(gdg) -> None:
    # The detector's input must not leak ground truth.
    for message in gdg.messages[:200]:
        dumped = message.model_dump()
        assert "conflict_type" not in dumped and "label" not in dumped


def test_generator_is_deterministic() -> None:
    # Freeze-once determinism comes from the seed: two builds are identical.
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "examples"))
    import make_gdg_fixture as g
    a, _ = g.build()
    b, _ = g.build()
    assert a == b  # build() returns plain dicts now
