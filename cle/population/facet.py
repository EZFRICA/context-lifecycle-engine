"""The agent facet: one sentence describing what an agent does.

Implements docs/proposals/facet-contract.md §a and §d. A facet is the first
prose in this project produced by a model from user text and then STORED, which
is why it is a type and not a string: the difference from free text has to be
mechanical, not documentary.

Four mechanisms, each failing loudly:

1. `Facet` is a frozen model whose validator refuses a text outside 40-300
   characters, or carrying a URL, a file path, a number longer than two digits,
   or a capitalised non-initial token. A `Facet` that violates them cannot exist.
2. `build_facet` also refuses a text sharing a span of six words or more with its
   sources - the check a prompt instruction cannot make, and the only one that
   needs the source, which is why it lives in the builder and not the type.
3. `build_facet` and `facet_from_record` are the only places a `Facet` is
   constructed. `tests/unit/test_population_facet.py` asserts it by AST.
4. There is no CLI flag that supplies a facet. The generator is the one writer.

A facet is DATA, not a derivation (§d-bis): generated once at the agent's birth,
never regenerated, and an agent born before facets existed never gets one.
`FacetStatus` is what makes "no facet because it failed" different from "no
facet because the agent predates facets" - the latter is an entry with no
status at all, which every write since facets exist carries.
"""

from dataclasses import dataclass
from typing import Any, Literal, Sequence

from pydantic import BaseModel, field_validator

from cle.population.leak import file_paths, long_numbers, proper_nouns, urls, verbatim_spans

FACET_MIN_CHARS = 40
FACET_MAX_CHARS = 300
#: A span of this many words shared with the source is a quotation, not a
#: description of a kind of task.
VERBATIM_SPAN_WORDS = 6

FacetStatus = Literal["present", "generation_failed"]
RefusalKind = Literal[
    "empty", "too_short", "too_long", "url", "file_path", "long_number",
    "proper_noun", "verbatim_span",
]


class FacetRefusedError(ValueError):
    """A generated text failed a mechanical check and cannot become a facet.

    Carries the KIND of refusal, a closed vocabulary, so the caller can record
    why without recording the text itself.
    """

    def __init__(self, kind: RefusalKind, detail: str) -> None:
        super().__init__(f"facet refused ({kind}): {detail}")
        self.kind: RefusalKind = kind


def refusal(text: str) -> tuple[RefusalKind, str] | None:
    """The checks a facet must pass on its own. `None` means it passes.

    The detail never quotes the text: a refusal is logged, and the refused text
    is exactly what must not reach a log that outlives the build.
    """
    stripped = text.strip()
    if not stripped:
        return "empty", "no text"
    if len(stripped) < FACET_MIN_CHARS:
        return "too_short", f"{len(stripped)} characters, minimum {FACET_MIN_CHARS}"
    if len(stripped) > FACET_MAX_CHARS:
        return "too_long", f"{len(stripped)} characters, maximum {FACET_MAX_CHARS}"
    checks = (("url", urls), ("file_path", file_paths),
              ("long_number", long_numbers), ("proper_noun", proper_nouns))
    for kind, check in checks:
        found = check(stripped)
        if found:
            return kind, f"{len(found)} match(es)"  # type: ignore[return-value]
    return None


class Facet(BaseModel, frozen=True):
    """A validated description of what one agent does. Engine-written only."""

    text: str
    #: Which generator produced it, model and prompt version included: a facet
    #: is data that cannot be recomputed, so its provenance travels with it.
    generator_id: str

    @field_validator("text")
    @classmethod
    def _mechanical(cls, value: str) -> str:
        found = refusal(value)
        if found is not None:
            raise ValueError(f"facet refused ({found[0]}): {found[1]}")
        return value.strip()

    @field_validator("generator_id")
    @classmethod
    def _named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a facet must name the generator that produced it")
        return value


def build_facet(text: str, *, sources: Sequence[str], generator_id: str) -> Facet:
    """The construction site of a new facet (contract §d, mechanism 3)."""
    found = refusal(text)
    if found is not None:
        raise FacetRefusedError(*found)
    if verbatim_spans(text, list(sources), n=VERBATIM_SPAN_WORDS):
        raise FacetRefusedError(
            "verbatim_span",
            f"shares a span of {VERBATIM_SPAN_WORDS} or more words with its source",
        )
    return Facet(text=text, generator_id=generator_id)


def facet_from_record(record: dict[str, Any]) -> Facet:
    """Read a facet back from a topology entry, re-validating it on the way.

    The second and last construction site. A record edited by hand so that it
    no longer passes the checks fails here, at read, rather than reaching a
    population report.
    """
    return Facet.model_validate(record)


@dataclass(frozen=True)
class FacetOutcome:
    """What happened when a facet was generated at birth."""

    facet: Facet | None
    status: FacetStatus
    #: Why it failed, when it did: a refusal kind, or `generator_error` when the
    #: generator itself raised. Never the text.
    failure: RefusalKind | Literal["generator_error"] | None
