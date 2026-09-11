"""The population layer's two privacy guards: the user floor and the name screen.

SCOPE: bucket 1 (embedder-agnostic). Everything here is about which groups may be
named and which names may be shown; no vector space is involved.

WHAT THESE DO NOT CLAIM: that the floor is sufficient. BLUEPRINT §7c says a single
global floor is insufficient and knows why - a rare name identifies a team long
before any global count is reached. These pin the floor that exists, against the
ways it was actually observed to fail.
"""

import pytest

from cle.population.naming import name_groups
from cle.population.privacy import (
    MIN_GROUP,
    MIN_USERS,
    NAME_MAX,
    clean_name,
    describable,
    name_is_safe,
    shown_name,
)


class _Namer:
    """Returns fixed raw names and records which groups it was shown."""

    namer_id = "test:fixed"

    def __init__(self, raw: dict[int, str]) -> None:
        self.raw = raw
        self.seen: dict | None = None

    def name(self, groups):
        self.seen = dict(groups)
        return {g: self.raw.get(g, "") for g in groups}


# --- the k-anonymity floor ------------------------------------------------

def test_a_big_group_from_too_few_people_may_not_be_named() -> None:
    """Six members is plainly big enough to describe. They came from two people."""
    members = {7: ["a", "b", "c", "d", "e", "f"]}
    assert len(members[7]) >= MIN_GROUP
    assert describable(members, {7: {"alice", "bob"}}) == {}


def test_the_same_group_may_be_named_once_enough_people_produced_it() -> None:
    members = {7: ["a", "b", "c", "d", "e", "f"]}
    assert describable(members, {7: {"alice", "bob", "carol"}}) == members


def test_the_floor_is_counted_over_distinct_users_not_members() -> None:
    """One person may not clear the floor by being prolific."""
    assert describable({1: ["x"] * (MIN_USERS + 5)}, {1: {"solo"}}) == {}


def test_a_small_group_from_many_people_may_not_be_named_either() -> None:
    users = {2: {f"user{i}" for i in range(MIN_USERS + 4)}}
    assert describable({2: ["only-one"]}, users) == {}


def test_a_group_with_no_recorded_users_is_refused_not_defaulted() -> None:
    assert describable({3: ["a", "b", "c", "d"]}, {}) == {}


def test_a_group_below_the_floor_is_never_even_sent_to_the_namer() -> None:
    """The namer is a model call: a group too small to show is not shown to it."""
    members = {1: ["a", "b", "c"], 2: ["d", "e", "f"]}
    users = {1: {"p", "q", "r"}, 2: {"p", "q"}}
    namer = _Namer({1: "planning_tasks", 2: "never_shown"})

    outcome = name_groups(members, users, namer)

    assert set(namer.seen) == {1}
    assert outcome.names == {1: "planning_tasks"}
    assert outcome.below_user_floor == 1
    assert 2 in members, "the suppressed group keeps its existence; only its name goes"


# --- the identifier screen ------------------------------------------------

def test_a_name_carrying_a_proper_noun_is_refused() -> None:
    assert not name_is_safe("questions_from_Dupont")


def test_a_name_carrying_a_long_number_is_refused() -> None:
    """Underscores are spaced first: `\\b` sees no boundary between `_` and a digit."""
    assert not name_is_safe("ticket_84915720394_triage")


def test_an_ordinary_name_survives_the_screen() -> None:
    assert name_is_safe("javascript_debugging_tasks")


def test_a_proper_noun_in_the_raw_name_is_refused_through_the_whole_pipeline() -> None:
    """The defect `shown_name` closes, pinned where it lived: the full path.

    `clean_name` lowercases. Screening only its output left the proper-noun check
    nothing to find, so `tickets for Dupont` came out as `tickets_for_dupont` and
    was shown. `name_is_safe` alone was always right; the pipeline never asked it
    about the string that still had the capital.
    """
    assert name_is_safe(clean_name("tickets for Dupont")), "lowercasing hides the name"
    assert shown_name("tickets for Dupont") == ""

    outcome = name_groups({1: ["a", "b", "c"]}, {1: {"p", "q", "r"}},
                          _Namer({1: "tickets for Dupont"}))
    assert outcome.names == {}
    assert outcome.refused == 1


def test_a_long_number_is_refused_in_either_form() -> None:
    assert shown_name("ticket 84915720394 triage") == ""
    assert shown_name("ticket_84915720394_triage") == ""


# --- normalisation: the string shown is the string screened ---------------

def test_a_compliant_name_comes_out_as_its_cleaned_form() -> None:
    assert shown_name("  event planning assistance\nsecond line  ") == "event_planning_assistance"
    assert clean_name(clean_name("Debugging Java Errors")) == clean_name("Debugging Java Errors")


def test_the_cap_cuts_on_a_word_boundary_and_never_mid_word() -> None:
    long_name = "recurring_newsletter_drafting_for_chapter_members"
    cleaned = clean_name(long_name)
    assert len(cleaned) <= NAME_MAX
    assert not cleaned.endswith("_")
    assert all(part in long_name.split("_") for part in cleaned.split("_")), (
        f"{cleaned!r} invented a word the generator never wrote"
    )


def test_a_three_word_name_is_not_truncated() -> None:
    for name in ("recurring_newsletter_drafting", "speaker_invitation_management"):
        assert clean_name(name) == name


def test_a_single_word_over_the_cap_is_refused_rather_than_sliced() -> None:
    assert clean_name("a" * (NAME_MAX + 5)) == ""


@pytest.mark.parametrize("raw", ["", "   ", "\n", None])
def test_an_empty_generation_yields_no_name(raw) -> None:
    assert clean_name(raw) == ""
    assert shown_name(raw) == ""


def test_the_cap_is_a_pinned_decision_not_a_free_parameter() -> None:
    """Every other assertion tracks NAME_MAX, so none of them bounds it.

    Three real words already reach 29 characters; under 30 truncates correct
    answers, over 60 is prose.
    """
    assert 30 <= NAME_MAX <= 60


def test_a_live_name_in_content_parts_is_read_as_its_text() -> None:
    """Same live answer shape as the facet; a repr would never be a clean name."""
    from types import SimpleNamespace

    from cle.population.naming import LiveNamer

    class Parts:
        def invoke(self, prompt):
            return SimpleNamespace(content=[{"type": "text", "text": "event_planning_tasks"}])

    live = object.__new__(LiveNamer)
    live._llm = Parts()
    live.namer_id = "live:test:name-prompt-v1"

    outcome = name_groups({1: ["a", "b", "c"]}, {1: {"p", "q", "r"}}, live)
    assert outcome.names == {1: "event_planning_tasks"}
