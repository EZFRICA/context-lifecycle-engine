"""Holdout history generator — a process-independent discovery source.

PROCESS INDEPENDENCE — what this module deliberately does NOT share with
cle/detect (the whole point; it breaks the circularity of make_fixture.py,
which plants patterns with the SAME embedder the detector uses):

  * It imports NOTHING from `cle` — pure stdlib. It emits plain prompt-history
    dicts; the detector processes them blind.
  * It does NOT use the embedder, the dimension (64), the cosine threshold
    (0.6), the min_signal_occurrences gate, DetectorConfig, or any centroid.
  * Patterns come from domain knowledge of a DIFFERENT organiser's week (a
    Nairobi GDG lead, distinct voice from the Abidjan ground-truth fixture),
    not from inspecting what the detector will find.

FREEZE-ONCE + realistic (the realism run): openers are genuinely varied
(>= 8 distinct per recurring pattern), timing is irregular, closers vary, and
some episodes have no closer. Determinism comes from the committed .jsonl and
a fixed seed. Whether the detector RECOVERS these patterns from realistic
paraphrase is exactly what the discovery test MEASURES — and reports, never
tunes. (On realistic data the v1 bag-of-tokens embedder fragments paraphrase
badly; expect discovery to drop. That is a finding about the detector.)

Run:  .venv/bin/python examples/make_holdout.py
Writes examples/prompt_history_holdout.jsonl.
"""

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent
T0 = datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc)
WEEKS = 16
DAYS = WEEKS * 7
SEED = 424242

# Recurring patterns — the organiser's own voice, distinct from the Abidjan
# ground-truth banks. >= 8 varied phrasings each so the DATA is non-templated
# regardless of whether the detector clusters them.
MEETUP_PREP = [
    "draft the agenda for next months nairobi gdg meetup",
    "we need a run of show for the community night, start it",
    "faut preparer le programme du prochain meetup",
    "block out the talks and breaks for the monthly gathering",
    "put together the evening schedule for our devfest warmup",
    "sketch the meetup agenda, keep some buffer for networking",
    "what is the running order for the next community evening",
    "plan the sessions and timing for the monthly meetup",
    "organise the meetup programme, lightning talks first",
    "prep the agenda for the gdg night, add a demo slot",
]
OUTREACH = [
    "write a speaker invite email for our upcoming gdg session",
    "reach out to that ml engineer about giving a talk",
    "faut contacter une intervenante pour la session",
    "email a prospective speaker for the next devfest",
    "draft an invitation to someone to present at the meetup",
    "ping a few candidates about speaking this month",
    "compose an outreach note to a potential presenter",
    "invite the person who did the flutter talk to come back",
    "send a warm email asking someone to headline the session",
    "ask around and email a speaker for the community night",
]
VENUE = [  # costly, reformulation-prone: usually no closer
    "help me draft the venue booking request for the gdg event",
    "the venue form needs headcount and av requirements added",
    "how do i phrase the insurance clause the venue manager wants",
    "redo the booking request, they need a contingency for reschedule",
    "the space quote seems high, help me push back politely",
    "chase the venue again, they still havent confirmed the date",
    "rework the booking email, add the parking and access details",
    "the venue keeps changing terms, summarise where we landed",
    "draft another reservation request for a backup location",
    "sort the deposit wording for the venue contract",
]
FOLLOWUPS = [
    "keep it short and friendly", "add the rsvp link", "cc the co organiser",
    "make the tone warm", "mention we cover transport", "double check the date",
    "leave room for q and a", "flag anything blocking",
]
NOISE = [
    "write a twitter thread announcing the meetup",
    "reply to a sponsor asking about attendee demographics",
    "review the draft budget for the q2 events",
    "suggest icebreakers for a mixed technical crowd",
    "write a post event thank you to the speaker",
    "collect feedback from attendees after the meetup",
    "draft a linkedin recap of the session highlights",
    "create a speaker bio template for the website",
    "write an rsvp reminder for two days before",
    "summarise the action items from the planning call",
    "review the community guidelines document",
    "draft a call for speakers for next quarter",
    "help reply to a venue quote that seems too expensive",
    "note to self renew the meetup dot com subscription",
]
CLOSERS = ["thanks", "asante", "perfect", "ok got it", "great", None, None, None]


class Builder:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.msgs = []
        self.hours_used = {}

    def at(self, day):
        used = self.hours_used.setdefault(day, set())
        choices = [h for h in range(7, 22) if h not in used]
        hour = self.rng.choice(choices) if choices else self.rng.randint(7, 21)
        used.add(hour)
        return T0 + timedelta(days=day, hours=hour, minutes=self.rng.randint(0, 12))

    def episode(self, day, thread, opener, *, followups=(), force_close=None):
        ts = self.at(day)
        self.msgs.append({"user_id": "gdg_organiser", "ts": ts.isoformat(),
                          "text": opener, "thread_id": thread})
        for f in followups:
            ts = ts + timedelta(minutes=self.rng.randint(1, 10))
            self.msgs.append({"user_id": "gdg_organiser", "ts": ts.isoformat(),
                              "text": f, "thread_id": thread})
        close = force_close if force_close is not None else (self.rng.choice(CLOSERS) is not None)
        if close:
            ts = ts + timedelta(minutes=self.rng.randint(1, 10))
            self.msgs.append({"user_id": "gdg_organiser", "ts": ts.isoformat(),
                              "text": self.rng.choice(CLOSERS) or "thanks", "thread_id": thread})

    def draw(self, bank, used):
        pool = used[0]
        if not pool:
            pool = bank[:]
            self.rng.shuffle(pool)
        used[0] = pool
        return pool.pop()

    def some(self, k_max=3):
        return self.rng.sample(FOLLOWUPS, self.rng.randint(0, k_max))


def holdout_history() -> list[dict]:
    b = Builder(SEED)
    used_prep, used_out, used_ven = [[]], [[]], [[]]
    # A. monthly meetup prep — 2 prep sessions/month over 4 months (~8), varied.
    for occ, day in enumerate(range(2, DAYS, 13)):
        b.episode(day, f"meetup-prep-{occ}", b.draw(MEETUP_PREP, used_prep),
                  followups=b.some())
    # B. speaker outreach — ~fortnightly, short threads (>= 8).
    for occ, day in enumerate(range(4, DAYS, 12)):
        b.episode(day, f"outreach-{occ}", b.draw(OUTREACH, used_out),
                  followups=b.some(2))
    # C. venue friction — costly, usually no closer (reformulation candidate).
    for occ, day in enumerate(range(6, DAYS, 13)):
        b.episode(day, f"venue-{occ}", b.draw(VENUE, used_ven),
                  followups=b.rng.sample(FOLLOWUPS, 3), force_close=False)
    # D. one-off noise.
    for occ, day in enumerate(range(1, DAYS, 8)):
        b.episode(day, f"noise-{occ}", b.rng.choice(NOISE), followups=[])
    return sorted(b.msgs, key=lambda m: m["ts"])


def main() -> None:
    messages = holdout_history()
    path = EXAMPLES / "prompt_history_holdout.jsonl"
    path.write_text("\n".join(json.dumps(m) for m in messages) + "\n")
    span = (datetime.fromisoformat(messages[-1]["ts"]) - datetime.fromisoformat(messages[0]["ts"])).days
    print(f"wrote {path.name}: {len(messages)} messages across ~{span} days")
    print("recurring patterns (unknown to the detector): meetup-prep, outreach, venue")


if __name__ == "__main__":
    main()
