"""The mechanical leak checks of the facet contract (§a, §d), pure.

Nothing here touches a model, a network or a file. That is the property that
lets a guard built on them run in the offline suite, and it is why they live in
the engine rather than in a bench module: a bench builds a BigQuery client, and
a guard must never need credentials to be imported.

The checks are deliberately crude. §d asks for a MECHANICAL check, and a
mechanical check that needs a model to run is not one. They over-count (any
capitalised technical term, an acronym) and under-count (a lowercase product
name, a name in a script without case). They narrow the channel; they do not
close it, and anyone reading an aggregate built on them must know that.
"""

import re

#: Words that begin a sentence, or are otherwise capitalised for grammar rather
#: than because they name something. Counting these as proper nouns would make
#: every facet look like a leak.
_STOP_CAPS = {"A", "An", "The", "This", "These", "Their", "It", "In", "On", "For",
              "To", "By", "With", "When", "Where", "How", "What", "If", "And", "Or"}

#: What a redacted proper noun becomes. A placeholder rather than a deletion:
#: dropping the word would leave "configure the web server" and "configure the
#: web server" indistinguishable whether the original said Apache or nginx, which
#: silently merges two different tasks. The marker keeps the slot.
REDACTION = "SYSTEM"

_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|org|net|io|dev|ai|fr|co)\b")
_PATH = re.compile(
    r"(?:^|\s)(?:~?/|\.{1,2}/|[A-Za-z]:\\)\S+"
    r"|\b[\w-]+\.(?:py|js|ts|json|ya?ml|csv|txt|md|sql|sh|java|cpp|go|rs|html|css)\b"
)


def proper_nouns(text: str) -> list[str]:
    """Capitalised words that are not sentence-initial and not grammar words."""
    words = text.split()
    return [w.strip(".,;:()") for i, w in enumerate(words)
            if i > 0 and w[:1].isupper()
            and w.strip(".,;:()") not in _STOP_CAPS
            # The redaction marker is capitalised by construction. Counting it
            # would make a redacted text score as leaking its own placeholder.
            and w.strip(".,;:()") != REDACTION]


def long_numbers(text: str) -> list[str]:
    """Numbers longer than two digits - §a forbids them as an identifier channel.

    Callers must pass text whose separators are SPACES. `\\b` treats `_` as a word
    character, so `ticket_84915720394_triage` matches nothing; an
    underscore-joined name has to be spaced first (see `privacy.name_is_safe`).
    """
    return re.findall(r"\b\d{3,}\b", text)


def urls(text: str) -> list[str]:
    """Web addresses, with or without a scheme."""
    return [m.group(0) for m in _URL.finditer(text)]


def file_paths(text: str) -> list[str]:
    """Absolute, relative or drive paths, and bare file names with an extension."""
    return [m.group(0).strip() for m in _PATH.finditer(text)]


def verbatim_spans(facet: str, sources: list[str], n: int = 6) -> int:
    """Count n-grams the facet copies verbatim from its own source text.

    The sharpest of the checks: a facet describes a KIND of task, so any
    six-word span lifted from the instance is the failure the contract names.
    """
    fac = facet.lower().split()
    grams = {" ".join(fac[i:i + n]) for i in range(max(0, len(fac) - n + 1))}
    hit = 0
    for s in sources:
        toks = s.lower().split()
        src = {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}
        hit += len(grams & src)
    return hit


def redact(text: str) -> str:
    """Apply the checks as a TRANSFORM rather than a refusal.

    The contract specifies them as guards that reject a facet, and that is what
    `facet.build_facet` does. Rejection cannot be MEASURED, though - a rejected
    facet has no vector - so the benches redact instead, which keeps every facet
    and asks what closing the leak channel costs the grouping.
    """
    out = []
    for i, word in enumerate(text.split()):
        bare = word.strip(".,;:()")
        if i > 0 and word[:1].isupper() and bare not in _STOP_CAPS:
            out.append(REDACTION)
        elif re.fullmatch(r"\d{3,}", bare):
            out.append(REDACTION)
        else:
            out.append(word)
    return " ".join(out)
