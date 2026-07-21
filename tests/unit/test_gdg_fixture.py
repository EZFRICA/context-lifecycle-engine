"""GDG fixture structural sanity + label targeting (sidecar-driven)."""

import pytest


def test_scale(gdg) -> None:
    assert len(gdg.episodes) >= 300
    span = (gdg.messages[-1].ts - gdg.messages[0].ts).days
    assert 44 <= span <= 46


@pytest.mark.parametrize("domain,tool", [("events", "calendar_api"),
                                         ("speakers", "outreach_email"),
                                         ("sponsors", "sponsor_crm"),
                                         ("community", None)])
def test_domain_tool_needs_are_realistic(gdg, domain, tool) -> None:
    assert gdg.ground["domains"][domain]["tool"] == tool
    if tool:
        opener = gdg.ground["domains"][domain]["opener"]
        _, eps = gdg.cluster_of(opener)
        assert all(e.required_tool == tool for e in eps)


def test_community_episodes_carry_no_tool(gdg) -> None:
    toolless = [e for e in gdg.episodes if e.required_tool is None]
    assert len(toolless) > 100  # Q&A + noise dominate the tool-less side


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


def test_generator_is_deterministic(gdg) -> None:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "examples"))
    import make_gdg_fixture as g
    a, _ = g.build()
    b, _ = g.build()
    assert [m.model_dump() for m in a] == [m.model_dump() for m in b]
