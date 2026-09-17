"""Who writes a facet, and what happens when writing it fails.

`FacetGenerator` is a Protocol with two implementations, mirroring the
fingerprinter's substrate choice in `cle build --model-id`:

  * `StubFacetGenerator` - deterministic and offline, for `stub-*` model ids,
    the suite and the CI loop. A template over the sources' own content words,
    not a model.
  * `LiveFacetGenerator` - the configured model, with the prompt of contract §b.

A failed generation never blocks a birth. A facet is not evidence (contract §e):
it gates nothing, so an agent whose facet could not be produced is still born,
carrying `facet_status: generation_failed` and the KIND of the failure.
"""

from typing import Protocol, Sequence

from cle.logs import get_logger
from cle.population.facet import FacetOutcome, FacetRefusedError, build_facet
from cle.population.lexical import content_words

logger = get_logger(__name__)

#: Bump when the prompt changes: a facet's provenance names it, and two facets
#: from two prompts are two measurements.
FACET_PROMPT_VERSION = "facet-prompt-v1"

#: The prompt of contract §b, in its own words. It is the WEAKEST link in the
#: design and is named as such there: `build_facet` refuses what it lets through.
FACET_PROMPT = """You write ONE sentence describing what an automated assistant does, \
from examples of the requests it handles.

Rules:
- Describe the KIND of task the requests share, not any single request.
- Start with a verb. English. Between 40 and 300 characters.
- Reproduce no private information. Name no person, company, product or place.
- No numbers longer than two digits. No web addresses. No file names or paths.
- Do not quote the requests.
- The sentence is read by someone who never sees the requests, so it must make \
sense on its own.

Requests:
{requests}

Sentence:"""

#: How many source requests the live prompt shows.
MAX_PROMPT_SOURCES = 12


class FacetGenerator(Protocol):
    generator_id: str

    def generate(self, sources: Sequence[str]) -> str: ...


class StubFacetGenerator:
    """Deterministic stand-in: a fixed template over three content words.

    The words are lowercase and alphabetic, so the result passes the capital
    and digit checks by construction, and three words separated by commas cannot
    form a six-word span of any source.
    """

    generator_id = f"stub:facet-template:{FACET_PROMPT_VERSION}"

    def generate(self, sources: Sequence[str]) -> str:
        words = content_words(sources, limit=3)
        if len(words) == 3:
            return f"Handles a recurring request about {words[0]}, {words[1]} and {words[2]}."
        if words:
            return f"Handles a recurring request about {', '.join(words)}, again and again."
        return "Handles a recurring request this user makes again and again."


class LiveFacetGenerator:
    """The configured model at temperature 0, with the contract §b prompt.

    Determinism is NOT required here (contract §c): a facet is generated once and
    stored, and nothing ever regenerates it to compare. Temperature 0 is kept
    because a sampler adds variance and buys nothing.
    """

    def __init__(self, model_override: str | None = None) -> None:
        # Imported here: `cle.llm_provider` loads `.env` at import, which the
        # offline suite must never trigger by importing this module.
        from cle.llm_provider import GEMINI_MODEL, get_fingerprint_llm

        self._llm = get_fingerprint_llm(model_override)
        self.generator_id = f"live:{model_override or GEMINI_MODEL}:{FACET_PROMPT_VERSION}"

    def generate(self, sources: Sequence[str]) -> str:
        # The same reader the fingerprinter uses. Gemini answers with a LIST of
        # content parts (`[{'type': 'text', 'text': ...}]`); `str()` on that list
        # stored its Python repr as the facet, and the repr passed the checks,
        # because a word after a quote is not "capitalised" to the heuristic.
        from cle.build.fingerprinter import response_text

        requests = "\n".join(f"- {s}" for s in list(sources)[:MAX_PROMPT_SOURCES])
        response = self._llm.invoke(FACET_PROMPT.format(requests=requests))
        text = response_text(getattr(response, "content", response))
        return text.strip().split("\n")[0].strip()


def facet_at_birth(generator: FacetGenerator, sources: Sequence[str]) -> FacetOutcome:
    """Generate and validate one facet. Never raises: a birth must not fail on prose.

    A generator that raises (a network error, a quota) and a text the checks
    refuse both land as `generation_failed`, with the kind of failure and never
    the text - the refused text is precisely what must not be stored anywhere.
    """
    try:
        text = generator.generate(list(sources))
    except Exception as error:  # any generator failure is a recorded outcome, not a crash
        # The topology keeps only `generator_error`; the log keeps which error it
        # was. Never the sources, never what the generator returned.
        logger.warning("facet generation failed at birth (%s); recorded as generator_error",
                       type(error).__name__)
        return FacetOutcome(facet=None, status="generation_failed", failure="generator_error")
    try:
        facet = build_facet(text, sources=list(sources), generator_id=generator.generator_id)
    except FacetRefusedError as error:
        return FacetOutcome(facet=None, status="generation_failed", failure=error.kind)
    return FacetOutcome(facet=facet, status="present", failure=None)
