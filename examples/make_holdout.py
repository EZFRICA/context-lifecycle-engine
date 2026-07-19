"""Holdout history generator — a process-independent discovery source.

PROCESS INDEPENDENCE — what this module deliberately does NOT share with
cle/detect (this is the whole point; it breaks the circularity of
make_fixture.py, which plants patterns with the SAME embedder the detector
uses):

  * It imports NOTHING from `cle` — pure stdlib. It emits plain prompt-history
    dicts; the detector processes them blind. (The test converts them to the
    Message schema — that conversion is on the detector's side, not here.)
  * It does NOT use the embedder, so it cannot know the dimension (64) or which
    token hashes land in which buckets — it cannot reverse-engineer clusters.
  * It does NOT use the cosine threshold (0.6), the min_signal_occurrences (3)
    gate, DetectorConfig, or any centroid from make_fixture.py.
  * Patterns come from domain knowledge of a GDG (Google Developer Group)
    organiser's week, not from inspecting what the detector will find. It is
    hand-authored and deterministic — an LLM roleplaying the same organiser
    would give the same KIND of independence (no shared geometry); the
    hand-authored form keeps the discovery test reproducible offline.

Roles of the three sources: the fixture tests RECOVERY (planted patterns come
back), the adversarial fixture tests REJECTION (traps don't fire), and this
holdout tests DISCOVERY (unplanted patterns emerge). If the holdout produces
ugly numbers, report them — that is the point. Do not tune thresholds to make
it look good. (In practice the detector discovers 2 of the 3 authored patterns;
the monthly meetup thread is NOT recovered — a genuine surprise, left as-is.)

Run from the repo root:
    .venv/bin/python examples/make_holdout.py

Writes examples/prompt_history_holdout.jsonl.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent

# The GDG organiser starts their documented history on this anchor.
T0 = datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc)  # a Tuesday


def _msg(messages: list[dict], day: float, hour: float, text: str, thread: str) -> None:
    # A plain prompt-history record — the same shape cle.detect.episodes.Message
    # serialises to, but built here without importing it.
    messages.append(
        {
            "user_id": "gdg_organiser",
            "ts": (T0 + timedelta(days=day, hours=hour)).isoformat(),
            "text": text,
            "thread_id": thread,
        }
    )


def holdout_history() -> list[dict]:
    """≈ 85 days of a GDG chapter organiser's conversation history.

    Patterns the organiser repeats (not known to the detector in advance):
      A. Monthly meetup prep — every ~4 weeks, several clarifying turns.
      B. Speaker outreach — every ~2 weeks, short thread.
      C. Venue coordination — recurring friction with the same booking flow,
         multiple iterations each time (candidate for reformulation signal).
      D. One-off noise: social posts, sponsor emails, budget reviews, etc.
    """
    messages: list[dict] = []

    # ── A. Monthly meetup prep ────────────────────────────────────────────
    # 4 weeks × 4 turns each.  Opener is consistent, follow-ups vary.
    meetup_turns = [
        "draft the agenda for next month's gdg meetup",
        "add a lightning talk slot after the main session",
        "include rsvp instructions and the venue address",
        "thanks",
    ]
    for occ, anchor_day in enumerate([0, 28, 56, 84]):
        thread = f"meetup-prep-{occ}"
        for i, text in enumerate(meetup_turns):
            _msg(messages, anchor_day, 10.0 + i * 0.1, text, thread)

    # ── B. Speaker outreach ───────────────────────────────────────────────
    # Every ~2 weeks.  Short threads: opener + one follow-up + thanks.
    outreach_turns = [
        "write a speaker invite email for our upcoming gdg session",
        "make the subject line more specific to the talk topic",
        "thanks",
    ]
    for occ, anchor_day in enumerate([3, 17, 31, 45, 59, 73]):
        thread = f"outreach-{occ}"
        for i, text in enumerate(outreach_turns):
            _msg(messages, anchor_day, 14.0 + i * 0.1, text, thread)

    # ── C. Venue coordination friction (costly, no clean close) ──────────
    # 4 episodes, each 5–7 clarifying turns, no "thanks" — the user gives up
    # each time and comes back later (reformulation-signal candidate).
    venue_turns = [
        "help me draft the venue booking request for the gdg event",
        "the form needs the expected headcount and av requirements",
        "add a contingency clause in case we need to reschedule",
        "the venue manager wants insurance proof — how do i phrase that",
        "this is taking forever, can you summarise what we've agreed so far",
    ]
    for occ, anchor_day in enumerate([5, 19, 38, 60]):
        thread = f"venue-{occ}"
        for i, text in enumerate(venue_turns):
            _msg(messages, anchor_day, 16.0 + i * 0.15, text, thread)

    # ── D. One-off noise ──────────────────────────────────────────────────
    noise = [
        (1,  11.0, "write a twitter thread announcing the gdg meetup",  "social-1"),
        (6,  15.0, "help me reply to a sponsor asking about attendee demographics", "sponsor-1"),
        (10, 10.0, "review the draft budget for the q2 gdg events", "budget-q2"),
        (13, 14.0, "suggest icebreaker activities for a mixed technical crowd", "icebreaker"),
        (22, 9.0,  "write a post-event thank-you note to the speaker", "thankyou-1"),
        (25, 11.0, "help me collect feedback from attendees after the meetup", "feedback-1"),
        (33, 10.0, "draft a linkedin post recapping the gdg session highlights", "linkedin-1"),
        (40, 15.0, "create a speaker bio template for our website", "bio-template"),
        (47, 9.0,  "write a reminder email to rsvp holders two days before the event", "reminder-1"),
        (50, 14.0, "summarise the action items from the gdg planning call", "planning-call"),
        (54, 10.0, "help me reply to a venue quote that seems too expensive", "venue-quote"),
        (70, 11.0, "draft a call for speakers announcement for the next quarter", "cfp-q3"),
        (75, 9.0,  "review my community guidelines document for the gdg chapter", "guidelines"),
    ]
    for day, hour, text, thread in noise:
        _msg(messages, day, hour, text, thread)
        _msg(messages, day, hour + 0.1, "thanks", thread)

    # ISO timestamps share the same +00:00 offset and are zero-padded, so
    # lexicographic order is chronological.
    return sorted(messages, key=lambda m: m["ts"])


def main() -> None:
    messages = holdout_history()
    path = EXAMPLES / "prompt_history_holdout.jsonl"
    path.write_text("\n".join(json.dumps(m) for m in messages) + "\n")
    print(f"wrote {path.name}: {len(messages)} messages across ≈ 85 days")
    print("patterns (not known to the detector):")
    print("  A. monthly meetup prep   — 4 occurrences, 4-turn threads")
    print("  B. speaker outreach      — 6 occurrences, 3-turn threads")
    print("  C. venue coordination    — 4 occurrences, 5-turn (no close marker)")
    print("  D. one-off noise         — 13 threads")


if __name__ == "__main__":
    main()
