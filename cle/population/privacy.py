"""What a population output may show: the user floor, and the name screen.

BLUEPRINT §7c: an aggregate over a population must not become a way to read one
person's usage. Below the floor a group keeps its id, its size and its place in
the hierarchy, and loses only its NAME. Suppression, not a warning - a warning
leaves the name on screen and asks the reader to disregard it.

A single global floor is insufficient, and is known to be: a rare name can
identify a team long before any global count is reached, and one number cannot
express that. This is the floor that exists, not the one the problem requires.
"""

from typing import Mapping, Sequence

from cle.population.leak import long_numbers, proper_nouns

#: The k-anonymity floor, counted over DISTINCT USERS - one CLE instance is one
#: user. Clio states its threshold as "the number of unique users or
#: conversations"; counting clusters instead would let one prolific person, or
#: two people, name a group on their own.
MIN_USERS = 3

#: A group also has to have enough members to describe at all. Kept separate
#: from MIN_USERS because they guard different things: this one is about whether
#: a name would mean anything, the other about whether it may be shown.
MIN_GROUP = 3

#: A name is a label, not prose, so it is capped - on an UNDERSCORE, never
#: mid-word, because a cut word is a word the generator never wrote. 40 because
#: the prompt asks for two or three words and three real ones already reach 29
#: (`recurring_newsletter_drafting`); anything under 30 truncates correct
#: answers, anything over 60 is prose.
NAME_MAX = 40


def describable(members: Mapping[int, Sequence[str]],
                users: Mapping[int, set[str]]) -> dict[int, Sequence[str]]:
    """The groups that may be named at all: big enough AND from enough people.

    A group missing from this mapping is not dropped - it keeps its id and its
    place in the report, and only loses the right to a name. A group with no
    recorded users reads as zero users, never as unknown-so-allow.
    """
    return {g: m for g, m in members.items()
            if len(m) >= MIN_GROUP and len(users.get(g, set())) >= MIN_USERS}


def name_is_safe(name: str) -> bool:
    """Refuse a generated name that carries an identifier.

    Clio has a model verify its cluster summaries before display; this does the
    same job mechanically, because a prompt instruction is not a guard and
    neither is a second model's opinion of one.

    Both checks get the name with underscores turned back into spaces. For
    `long_numbers` that is not cosmetic: `\\b\\d{3,}\\b` finds no word boundary
    between `_` and a digit, and every name here is underscore-joined.
    """
    spaced = name.replace("_", " ")
    return not proper_nouns(spaced) and not long_numbers(spaced)


def shown_name(raw: str | None) -> str:
    """The name that may be shown for a raw generated name, or "" if none may.

    The screen runs on BOTH forms, and each one catches what the other cannot:

      * the RAW first line, because `clean_name` lowercases, and case is the only
        signal the proper-noun check has. Screening only the cleaned string made
        that check dead: `tickets for Dupont` became `tickets_for_dupont` and
        passed, because there was no capital left to find;
      * the CLEANED string, because it is the one that ships, and a guard that
        inspects a value other than the published one is not a guard.

    A generator that title-cases everything is refused rather than trusted:
    suppression over coverage, as everywhere on this boundary.
    """
    cleaned = clean_name(raw)
    first_line = (raw or "").strip().split("\n")[0]
    if not cleaned or not name_is_safe(first_line) or not name_is_safe(cleaned):
        return ""
    return cleaned


def clean_name(raw: str | None) -> str:
    """Normalise one generated name to the exact string that will be shown.

    Returns "" for anything unusable, which the caller reads as a refusal. A
    single word longer than NAME_MAX has no underscore to cut on and becomes "":
    refusing it is honest where slicing it would invent a word.
    """
    text = (raw or "").strip().split("\n")[0].strip().lower()
    text = "".join(ch for ch in text if ch.isalnum() or ch in "_ ").strip().replace(" ", "_")
    while len(text) > NAME_MAX:
        text = text.rpartition("_")[0]
    return text.strip("_")
