"""Clio stage 3: a name per group, floored and screened before it is shown.

`Namer` is a Protocol. The engine ships a deterministic `StubNamer` and a
`LiveNamer` on the configured model; `dashboard_level_2/discover_intents.py`
adds a BigQuery one. All three return RAW names, and `name_groups` is the only
path from a raw name to a shown one: the floor first, then normalisation, then
the identifier screen on the final string.
"""

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from cle.population.lexical import content_words
from cle.population.privacy import MIN_GROUP, describable, shown_name

#: How many members of a group the prompt shows.
MAX_PROMPT_MEMBERS = 10

NAME_PROMPT = """Below are short descriptions of tasks, all drawn from one group.

Give the group a NAME: two or three words, lowercase, joined by underscores.
It must describe what the whole group has in common, not any one member.

Use only what the descriptions say. If they have nothing in common, answer
mixed.

Descriptions:
{members}

Name:"""


class Namer(Protocol):
    namer_id: str

    def name(self, groups: Mapping[int, Sequence[str]]) -> dict[int, str]: ...


class StubNamer:
    """Deterministic: the two most frequent content words of the members."""

    namer_id = "stub:name-template-v1"

    def name(self, groups: Mapping[int, Sequence[str]]) -> dict[int, str]:
        names = {}
        for gid, members in groups.items():
            words = content_words(members, limit=2)
            names[gid] = "_".join(words) if words else "mixed"
        return names


class LiveNamer:
    """The configured model at temperature 0, one call per group."""

    def __init__(self, model_override: str | None = None) -> None:
        from cle.llm_provider import GEMINI_MODEL, get_fingerprint_llm

        self._llm = get_fingerprint_llm(model_override)
        self.namer_id = f"live:{model_override or GEMINI_MODEL}:name-prompt-v1"

    def name(self, groups: Mapping[int, Sequence[str]]) -> dict[int, str]:
        # Structured content parts, read as text - see LiveFacetGenerator.
        from cle.build.fingerprinter import response_text

        names = {}
        for gid, members in groups.items():
            shown = "\n".join(f"- {m}" for m in list(members)[:MAX_PROMPT_MEMBERS])
            response = self._llm.invoke(NAME_PROMPT.format(members=shown))
            names[gid] = response_text(getattr(response, "content", response))
        return names


@dataclass(frozen=True)
class NamingOutcome:
    names: dict[int, str]
    #: Big enough to describe, but produced by too few distinct users.
    below_user_floor: int
    #: Eligible, named by the namer, and refused by the screen or the cleaner.
    refused: int


def name_groups(members: Mapping[int, Sequence[str]], users: Mapping[int, set[str]],
                namer: Namer) -> NamingOutcome:
    """Name only what the floor allows, and show only what the screen passes.

    The namer never sees a group below the floor, so a group too small to show
    is never even sent to a model.
    """
    eligible = describable(members, users)
    below = sum(1 for g, m in members.items() if len(m) >= MIN_GROUP and g not in eligible)
    if not eligible:
        return NamingOutcome(names={}, below_user_floor=below, refused=0)
    raw = namer.name(eligible)
    names = {}
    for gid in eligible:
        text = shown_name(raw.get(gid))
        if text:
            names[gid] = text
    return NamingOutcome(names=names, below_user_floor=below, refused=len(eligible) - len(names))
