"""Word-level helpers: the free lexical baseline, and content-word extraction.

`jaccard` is the bar every level-2 method is measured against. On Stack
Overflow a free token overlap separated duplicates at 62.2% recall for 10.1%
false positives; a facet mechanism that cannot beat it has no reason to exist
(docs/proposals/facet-contract.md, "What this contract does not settle").
"""

import re
from collections import Counter
from typing import Iterable

#: Grammar words, and the words the stub facet template itself contributes, so a
#: stub name reflects what the members are about rather than how they were
#: phrased.
STOPWORDS = frozenset(
    "a an the and or of to in on for with from by at as is are be was were it its "
    "this that these those my me i you your we our can how do does what why when "
    "where which who not no into about over under than then them they their there "
    "here have has had will would should could just also more most some such only "
    "handles recurring request requests again".split()
)


def jaccard(a: str, b: str) -> float:
    """Token-set overlap of two texts, lowercased, split on whitespace."""
    sa, sb = set(a.lower().split()), set(b.lower().split())
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def content_words(texts: Iterable[str], *, limit: int) -> list[str]:
    """The most frequent lowercase alphabetic words of four letters or more.

    Ties break alphabetically, so the result is a pure function of the input.
    Digits and capitals never survive: the output is meant to sit next to the
    leak checks, not to test them.
    """
    counts = Counter(
        word
        for text in texts
        for word in re.findall(r"[a-z]{4,}", text.lower())
        if word not in STOPWORDS
    )
    return [word for word, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]
