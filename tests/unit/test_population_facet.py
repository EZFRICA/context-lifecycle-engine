"""The facet: a type, not a string (docs/proposals/facet-contract.md §a, §d).

SCOPE: bucket 1 (embedder-agnostic). These pin what text may become a facet, who
may construct one, and what a failed generation records. No vector space.
"""

import ast
from pathlib import Path

import pydantic
import pytest

from cle.population.facet import (
    FACET_MAX_CHARS,
    FACET_MIN_CHARS,
    Facet,
    FacetRefusedError,
    build_facet,
    facet_from_record,
)
from cle.population.generator import StubFacetGenerator, facet_at_birth

ROOT = Path(__file__).resolve().parent.parent.parent
GOOD = "Drafts the weekly project recap for a team, with blockers and progress."
SOURCES = ["write the weekly recap of my project for the team",
           "put together the weekly project recap for the team"]


def test_a_description_of_a_kind_of_task_becomes_a_facet() -> None:
    facet = build_facet(GOOD, sources=SOURCES, generator_id="test:v1")
    assert facet.text == GOOD
    assert facet.generator_id == "test:v1"


@pytest.mark.parametrize("text, kind", [
    ("", "empty"),
    ("Drafts recaps.", "too_short"),
    ("Drafts " + "weekly recaps for the team, " * 20, "too_long"),
    ("Drafts recaps and posts them to https://example.org for the whole team.", "url"),
    ("Drafts recaps and saves them as notes/recap.md for the whole team.", "file_path"),
    ("Drafts recaps for project 4821 and sends them to the whole team.", "long_number"),
    ("Drafts recaps for Dupont and sends them to the whole team every week.", "proper_noun"),
])
def test_each_mechanical_check_refuses_with_its_own_kind(text: str, kind: str) -> None:
    with pytest.raises(FacetRefusedError) as refused:
        build_facet(text, sources=[], generator_id="test:v1")
    assert refused.value.kind == kind


def test_the_bounds_are_the_contract_values() -> None:
    assert (FACET_MIN_CHARS, FACET_MAX_CHARS) == (40, 300)


def test_a_span_copied_from_the_source_is_refused() -> None:
    """The check only the builder can make, because only it has the source."""
    copied = "Handles it: write the weekly recap of my project, every single time."
    with pytest.raises(FacetRefusedError) as refused:
        build_facet(copied, sources=SOURCES, generator_id="test:v1")
    assert refused.value.kind == "verbatim_span"


def test_a_refusal_never_quotes_the_refused_text() -> None:
    """A refusal is logged; the text it refused is what must not be."""
    with pytest.raises(FacetRefusedError) as refused:
        build_facet("Drafts recaps for Dupont and sends them to the team each week.",
                    sources=[], generator_id="test:v1")
    assert "Dupont" not in str(refused.value)


def test_a_record_that_no_longer_passes_is_refused_at_read() -> None:
    """A topology edited by hand cannot smuggle prose into a population report."""
    with pytest.raises(pydantic.ValidationError):
        facet_from_record({"text": "tickets for Dupont", "generator_id": "test:v1"})
    with pytest.raises(pydantic.ValidationError):
        facet_from_record({"text": GOOD, "generator_id": "  "})
    assert facet_from_record({"text": GOOD, "generator_id": "test:v1"}).text == GOOD


def test_a_facet_is_constructed_in_exactly_one_module() -> None:
    """Contract §d, mechanism 3: a second construction path makes the rest decorative."""
    constructors = {"Facet", "Facet.model_validate", "Facet.model_construct"}
    sites = []
    for root in ("cle", "dashboard", "tools"):
        for path in (ROOT / root).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call) and ast.unparse(node.func) in constructors:
                    sites.append((path.relative_to(ROOT).as_posix(), ast.unparse(node.func)))
    assert sites, "the scrape found no construction at all - it is looking in the wrong place"
    assert {p for p, _ in sites} == {"cle/population/facet.py"}, sites


# --- generation at birth ----------------------------------------------------

def test_the_stub_generator_is_deterministic_and_passes_its_own_checks() -> None:
    generator = StubFacetGenerator()
    first, second = generator.generate(SOURCES), generator.generate(SOURCES)
    assert first == second
    build_facet(first, sources=SOURCES, generator_id=generator.generator_id)


def test_different_clusters_get_different_stub_facets() -> None:
    generator = StubFacetGenerator()
    other = ["diagnose the production latency spike on the checkout service"]
    assert generator.generate(SOURCES) != generator.generate(other)


def test_a_generator_that_raises_records_a_failure_and_never_raises() -> None:
    class Broken:
        generator_id = "test:broken"

        def generate(self, sources):
            raise ConnectionError("quota")

    outcome = facet_at_birth(Broken(), SOURCES)
    assert (outcome.facet, outcome.status, outcome.failure) == (None, "generation_failed",
                                                                 "generator_error")


def test_a_generated_text_the_checks_refuse_records_its_kind() -> None:
    class Leaky:
        generator_id = "test:leaky"

        def generate(self, sources):
            return "Drafts recaps for Dupont and sends them to the team each week."

    outcome = facet_at_birth(Leaky(), SOURCES)
    assert (outcome.facet, outcome.status, outcome.failure) == (None, "generation_failed",
                                                                 "proper_noun")


def test_a_passing_text_is_present_with_its_provenance() -> None:
    outcome = facet_at_birth(StubFacetGenerator(), SOURCES)
    assert outcome.status == "present" and outcome.failure is None
    assert isinstance(outcome.facet, Facet)
    assert outcome.facet.generator_id == StubFacetGenerator.generator_id


def test_a_live_answer_in_content_parts_becomes_its_text_not_its_repr() -> None:
    """The shape the live Gemini model actually returns, measured end to end.

    `response.content` is a list of parts, `[{'type': 'text', 'text': ...}]`.
    Read with `str()`, the facet stored was the Python repr of that list, and it
    passed every check. No model is called here: the generator is built without
    its constructor and handed a stand-in that answers in that shape.
    """
    from types import SimpleNamespace

    from cle.population.generator import LiveFacetGenerator

    class Parts:
        def invoke(self, prompt):
            return SimpleNamespace(content=[{"type": "text", "text": GOOD, "extras": {"x": 1}}])

    live = object.__new__(LiveFacetGenerator)
    live._llm = Parts()
    live.generator_id = "live:test:facet-prompt-v1"

    assert live.generate(SOURCES) == GOOD
    outcome = facet_at_birth(live, SOURCES)
    assert outcome.status == "present" and outcome.facet.text == GOOD
