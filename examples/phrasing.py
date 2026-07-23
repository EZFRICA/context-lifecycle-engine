"""Phrasing banks + a seeded episode assembler — the raw material for the
freeze-once fixtures.

Pure data and stdlib only: this module imports NOTHING from `cle`, so the
holdout generator (which must stay process-independent) can use it without
coupling to the detector. Determinism comes from the COMMITTED .jsonl the
generators freeze, not from this module — the generators seed a
`random.Random` and this module never touches a global RNG or the clock.

These banks are DELIBERATELY NOT calibrated to cluster under the v1
embedder. Realistic paraphrase does not co-cluster in bag-of-hashed-tokens
at cosine 0.6 — that is a measured finding about the detector, reported in
docs/METRICS.md, not something to engineer away by shaving the text down to
near-duplicates. The banks aim only for genuine human variety: register,
franglais, typos, word order, differing structure. Whether the detector
then recovers the planted intent is a question we MEASURE, never a
constraint we author to. The realism guard
(tests/unit/test_fixture_realism.py) asserts data properties grouped by the
PLANTED intent (from the sidecar), never by detected clusters.
"""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Iterable

# ── opener banks (>= 8 co-clustering variants per recurring intent) ─────────
# The francophone GDG Cloud Abidjan lead: lowercase, terse, franglais, typos.

OPENERS: dict[str, list[str]] = {
    # monthly meetup scheduling (calendar_api).
    "events": [
        "schedule the monthly gdg meetup in the main room",
        "book us a venue for next months gdg community meetup",
        "we still need somewhere to hold the april gdg session",
        "on doit trouver une salle pour le prochain meetup gdg",
        "can you lock in the date for the next devfest style meetup",
        "find a room big enough for the monthly gathering",
        "the meetup venue isnt sorted yet, deal with it pls",
        "reserve the co working space for our gdg night again",
        "need to nail down when and where the next meetup happens",
        "sort the logistics for the monthly google dev group meetup",
        "où est ce quon fait le meetup ce mois ci, trouve une salle",
        "get the main hall booked before the seats fill up",
    ],
    # weekly newsletter (no tool).
    "newsletter": [
        "write the weekly gdg newsletter digest for members",
        "draft this weeks community update email for everyone",
        "faut envoyer la newsletter hebdo aux membres du groupe",
        "put together the recap email for this weeks subscribers",
        "the members havent had an update in a while, write one",
        "time for the weekly digest, summarise whats coming up",
        "compose the community bulletin for the mailing list",
        "our newsletter is overdue again, draft something short",
        "prepare the weekly roundup for the gdg abidjan members",
        "ecris le petit mot hebdomadaire pour la communaute",
        "get a members update out before friday please",
        "weekly digest time, whats worth telling the community",
    ],
    # speaker outreach (outreach_email).
    "speakers": [
        "write a speaker invite email for the next gdg session",
        "reach out to that cloud engineer about giving a talk",
        "faut contacter un intervenant pour la prochaine session",
        "draft an invitation to a potential speaker for devfest",
        "email someone interesting to come present at the meetup",
        "we need a speaker lined up, send a couple of invites",
        "invite the woman who did the kubernetes talk last year",
        "ping a few people about speaking at the next event",
        "compose an outreach note to a prospective presenter",
        "envoie une invitation a un speaker pour le talk du mois",
        "ask around and email a candidate to headline the session",
        "get someone confirmed to speak, start with an email",
    ],
    # sponsor pipeline (sponsor_crm).
    "sponsors": [
        "update the sponsor pipeline notes after todays call",
        "log what the bank said about backing devfest this year",
        "note the follow up date for the telco sponsorship talk",
        "faut noter le retour du sponsor dans le suivi",
        "record where we are with each potential partner",
        "the sponsor tracker is stale, add todays conversation",
        "who owes us a reply on sponsorship, update the list",
        "capture the outcome of the meeting with the fintech",
        "keep the funding pipeline current after this weeks calls",
        "mets a jour le suivi des sponsors apres la reunion",
        "jot down the amount the startup offered to sponsor",
        "track the next steps for the cloud provider sponsorship",
    ],
    # routing A: meetup-night agenda.
    "agenda_meetup": [
        "prepare the agenda for the gdg meetup night",
        "what is the running order for the community evening",
        "draft the schedule for the monthly meetup programme",
        "faut preparer le deroule de la soiree meetup",
        "plan out the talks and breaks for the meetup night",
        "put together the evenings programme for attendees",
        "sort the timing of each slot for the community night",
        "we need a run sheet for the gdg evening",
    ],
    # routing B: workshop agenda.
    "agenda_workshop": [
        "draft the agenda for the hands on coding workshop",
        "plan the exercises and timing for the codelab session",
        "faut structurer latelier pratique de code",
        "what should the workshop cover, block out the morning",
        "prepare the lab instructions and schedule for the workshop",
        "lay out the coding session step by step for participants",
        "organise the practical workshop flow for the day",
        "build the run sheet for the developer workshop",
    ],
    # temporal: venue reservation policy.
    "venue_policy": [
        "sort out venue reservations before next months community event",
        "figure out where were holding the big community day",
        "the annual gathering needs a location locked in soon",
        "faut regler la reservation du lieu pour levenement",
        "deal with booking a space for the community celebration",
        "we havent secured a venue for the yearly event yet",
        "arrange somewhere to host the community wide gathering",
        "get the location sorted for the flagship event",
    ],
}

# ── follow-up / directive banks ─────────────────────────────────────────────
# Consistent-intent follow-ups (used for the non-contradiction body of each
# intent) — varied so directive cosines SPREAD (no degenerate single value).

FOLLOWUPS: dict[str, list[str]] = {
    "events": [
        "put it on a saturday evening if the hall is free",
        "add the rsvp link once the slot is confirmed",
        "make sure the projector and mics are in the room",
        "invite the core team to the calendar hold",
        "double check theres no clash with another booking",
        "block ninety minutes plus setup time",
    ],
    "newsletter": [
        "lead with the recap of last weeks turnout",
        "include the call for speakers near the top",
        "add the photos from the last session",
        "keep the tone friendly and short",
        "link the rsvp for the next meetup",
        "mention the new sponsor at the end",
    ],
    "speakers": [
        "make the subject line specific to the talk topic",
        "mention we cover travel within the city",
        "propose two possible dates in the email",
        "keep it warm but short",
        "attach the speaker guidelines pdf",
        "ask for their bio and talk title",
    ],
    "sponsors": [
        "log the renewal amount and the next follow up date",
        "flag the ones going cold for a nudge",
        "note who owns the relationship now",
        "add the contact we met at the call",
        "set a reminder for the quarterly review",
        "record the tier they are considering",
    ],
    "agenda_meetup": [
        "add the rsvp link and the venue address",
        "leave ten minutes for announcements",
        "put the lightning talks before the break",
        "list the speakers and their slots",
    ],
    "agenda_workshop": [
        "add the setup steps and the repo link",
        "leave time for the hands on exercise",
        "list the prerequisites at the top",
        "put the q and a at the end",
    ],
}

# Contradiction directive banks — each SIDE is itself varied, so the flip is a
# genuine spread of moderate/severe cosines, not one repeated sentence.
NEWSLETTER_SHORT = [  # intra_cluster side A
    "keep the digest short, three bullets max, no fluff",
    "trim it right down, just the essentials please",
    "make it a quick skim, short and punchy",
    "cut it to a few lines, people dont read long ones",
]
NEWSLETTER_LONG = [  # intra_cluster side B (opposes A)
    "make it long and detailed with full session summaries",
    "expand every section, give the whole write up",
    "go in depth, cover each talk thoroughly",
    "write the full narrative version, dont hold back",
]
VENUE_DIY = [  # temporal side A (earlier regime)
    "handle the logistics yourself and book everything directly",
    "just go ahead and sort it all without checking with me",
    "take care of the whole booking on your own",
    "you decide and book it, no need to ask",
]
VENUE_ASK = [  # temporal side B (later regime — the flip)
    "always ask me for approval before booking anything",
    "run every reservation past me first from now on",
    "dont commit to any venue until i sign off",
    "check with me before you book, every time",
]
# events world_state: consistent intent (confirm/adjust the booking), the
# DIFFERENCE is the frozen tool_result, not the user's directive.
EVENTS_CONFIRM = [
    "great, confirm the main room and send the calendar hold",
    "perfect, lock that slot and invite the team",
    "good, book it and drop the rsvp link",
    "confirm the hold and add it to the shared calendar",
]
EVENTS_REROUTE = [
    "no room free, find an alternative venue for that evening",
    "fully booked, look for another hall the same week",
    "no slot, try the co working space instead",
    "taken, sort a backup venue for the meetup",
]

CLOSERS: list[str | None] = [
    "thanks", "merci", "perfect", "ok got it", "great thanks", "parfait",
    None, None, None,  # a third of episodes end with no closer at all
]

# Community Q&A / noise — diverse one-offs (correctly do NOT recur/cluster).
QA_OPENERS = [
    "answer a member asking how to submit a lightning talk",
    "reply to the discord question about the next event date",
    "help a newcomer find the beginner study group",
    "respond to feedback about last weeks session audio",
    "someone asks if the workshop is beginner friendly",
    "a member wants the slides from the cloud run talk",
    "reply to the dm about volunteering at the next event",
    "answer whether we record the sessions",
    "help a student who missed the registration deadline",
    "reply about parking near the venue",
    "explique a un membre comment rejoindre le groupe whatsapp",
    "answer a question about the code of conduct",
]
NOISE = [
    "remind me to buy stickers for the swag table",
    "share a fun fact about gdg history",
    "whats a good icebreaker for tonight",
    "note to self check the wifi at the venue",
    "draft a thank you to the volunteers",
    "jot down an idea for a womentechmakers session",
    "look up the cost of a banner reprint",
    "pense a commander leau pour levenement",
]


def _closer(rng: random.Random) -> str | None:
    return rng.choice(CLOSERS)


def assemble_episode(
    rng: random.Random,
    *,
    user_id: str,
    start,  # datetime
    opener: str,
    followups: Iterable[str] = (),
    thread_id: str,
    requires_tool: str | None = None,
    tool_result: str | None = None,
    force_close: bool | None = None,
) -> list[dict]:
    """One episode as a list of message dicts, with irregular within-episode
    gaps (1–20 min, always under the 30-min silence floor) and a varied or
    absent closer. Returns plain dicts (no cle types) so any generator can
    serialise them."""
    msgs: list[dict] = []
    ts = start
    msgs.append({
        "user_id": user_id, "ts": ts.isoformat(), "text": opener,
        "thread_id": thread_id, "requires_tool": requires_tool, "tool_result": tool_result,
    })
    for f in followups:
        # 1–10 min between turns: irregular, but keeps an episode's whole span
        # under an hour so same-day episodes (each on its own hour slot) do
        # not interleave and fragment on thread change.
        ts = ts + timedelta(minutes=rng.randint(1, 10))
        msgs.append({
            "user_id": user_id, "ts": ts.isoformat(), "text": f,
            "thread_id": thread_id, "requires_tool": None, "tool_result": None,
        })
    close = force_close if force_close is not None else (_closer(rng) is not None)
    if close:
        marker = _closer(rng) or "thanks"
        ts = ts + timedelta(minutes=rng.randint(1, 20))
        msgs.append({
            "user_id": user_id, "ts": ts.isoformat(), "text": marker,
            "thread_id": thread_id, "requires_tool": None, "tool_result": None,
        })
    return msgs
