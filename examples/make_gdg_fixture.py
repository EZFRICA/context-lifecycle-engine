"""GDG organizer fixture — the enriched ground-truth (recovery) source.

~300 episodes over 45 days, one organizer, four domains with distinct tool
needs, plus LABELED contradictions of all four types. Deterministic; tools
are declarations only (requires_tool / frozen tool_result decor — nothing
is executed).

Outputs:
- prompt_history_gdg.jsonl  — what the detector sees (NO labels).
- gdg_ground_truth.json     — test-side sidecar: conflict labels by thread,
  planted patterns, per-domain tool. The detector must never read this.
- tool library YAMLs under components/ already exist? No — tools are seeded
  by the demo via examples/gdg_tools/ (one YAML per tool declaration).

Run: .venv/bin/python examples/make_gdg_fixture.py
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cle.detect.episodes import Message  # noqa: E402  (data carrier)

EX = Path(__file__).resolve().parent
T0 = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
DAYS = 45

DOMAINS = {
    "events":   {"opener": "schedule the monthly gdg meetup in the main room",
                 "tool": "calendar_api", "every": 1, "hour": 9},
    "speakers": {"opener": "write a speaker invite email for the next gdg session",
                 "tool": "outreach_email", "every": 2, "hour": 11},
    "sponsors": {"opener": "update the sponsor pipeline notes after today's call",
                 "tool": "sponsor_crm", "every": 3, "hour": 15},
    # community Q&A: NO tool.
    "community": {"opener": None, "tool": None, "every": 1, "hour": 18},
}
QA_OPENERS = [
    "answer a member asking how to submit a lightning talk",
    "reply to the discord question about the next event date",
    "help a newcomer find the beginner study group",
    "respond to feedback about last week's session audio",
]
NOISE = ["thanks for everything today", "ok noted", "share a fun fact about gdg history",
         "what's a good icebreaker for tonight", "remind me to buy stickers"]


def _ep(msgs, ground, day, hour, opener, followups, thread, *, tool=None, result=None,
        label=None, close=True):
    ts = T0 + timedelta(days=day, hours=hour)
    msgs.append(Message(user_id="gdg", ts=ts, text=opener, thread_id=thread,
                        requires_tool=tool, tool_result=result))
    for k, f in enumerate(followups):
        msgs.append(Message(user_id="gdg", ts=ts + timedelta(minutes=3 * (k + 1)),
                            text=f, thread_id=thread))
    if close:
        msgs.append(Message(user_id="gdg", ts=ts + timedelta(minutes=3 * (len(followups) + 1)),
                            text="thanks", thread_id=thread))
    if label:
        ground["labeled_threads"][thread] = label


def build() -> tuple[list[Message], dict]:
    msgs: list[Message] = []
    ground: dict = {
        "labeled_threads": {},
        "domains": {k: {"tool": v["tool"], "opener": v["opener"]} for k, v in DOMAINS.items()},
        "patterns": {},
    }

    # ── four domains ────────────────────────────────────────────────────
    for day in range(DAYS):
        d = DOMAINS["events"]
        # tool_result alternates deterministically — WORLD decor. The two
        # labeled world_state pairs are days (10,11) and (30,31).
        result = "slot_free" if day % 2 == 0 else "no_slot"
        follow = ("great confirm the main room booking and send the invites"
                  if result == "slot_free"
                  else "no room free find an alternative venue for the meetup evening")
        label = "world_state" if day in (10, 11, 30, 31) else None
        _ep(msgs, ground, day, d["hour"], d["opener"], [follow], f"events-{day}",
            tool=d["tool"], result=result, label=label)

        if day % DOMAINS["speakers"]["every"] == 0:
            _ep(msgs, ground, day, 11, DOMAINS["speakers"]["opener"],
                ["make the subject line specific to the talk topic"],
                f"speakers-{day}", tool="outreach_email")
        if day % DOMAINS["sponsors"]["every"] == 0:
            _ep(msgs, ground, day, 15, DOMAINS["sponsors"]["opener"],
                ["log the renewal amount and the next follow up date"],
                f"sponsors-{day}", tool="sponsor_crm")
        # community Q&A: 2/day, varied openers, no tool.
        for slot in range(3):
            _ep(msgs, ground, day, 18 + slot, QA_OPENERS[(day + slot) % len(QA_OPENERS)],
                [], f"qa-{day}-{slot}")

    # ── intra_cluster contradiction ×2 (newsletter digest, close in time) ─
    news = "write the weekly gdg newsletter digest for members"
    for day, style, lab in [(5, "keep the digest short three bullets maximum no fluff", "intra_cluster"),
                            (8, "make the digest long and detailed with full session summaries", "intra_cluster"),
                            (22, "keep the digest short three bullets maximum no fluff", "intra_cluster"),
                            (25, "make the digest long and detailed with full session summaries", "intra_cluster")]:
        _ep(msgs, ground, day, 13, news, [style], f"news-{day}", label=lab)
    ground["patterns"]["newsletter"] = {"opener": news, "expected": "unstable_no_candidate"}

    # ── temporal evolution (venue booking policy, weeks apart) ───────────
    plan = "sort out venue reservations before next month's community event"
    for day in (2, 4, 6):
        _ep(msgs, ground, day, 16, plan,
            ["handle the logistics yourself and book everything directly"],
            f"plan-{day}", label="temporal")
    for day in (33, 36, 39, 42):
        _ep(msgs, ground, day, 16, plan,
            ["always ask me for approval before booking anything"],
            f"plan-{day}", label="temporal")
    ground["patterns"]["venue_policy"] = {"opener": plan, "expected": "candidate_from_recent"}

    # ── routing pair: two near clusters competing ────────────────────────
    r1 = "prepare the agenda for the gdg meetup night"
    r2 = "draft the workshop agenda for the coding session"
    for day in (7, 14, 21, 28, 35):
        _ep(msgs, ground, day, 10, r1, ["add the rsvp link and the venue address"],
            f"agenda-m-{day}", label="routing")
        _ep(msgs, ground, day + 1, 10, r2, ["add the rsvp link and the schedule details"],
            f"agenda-w-{day}", label="routing")
    ground["patterns"]["routing_pair"] = {"openers": [r1, r2]}

    # ── noise: one-offs, short acks, abandoned threads ───────────────────
    for day in range(0, DAYS):
        _ep(msgs, ground, day, 20, NOISE[day % len(NOISE)], [], f"noise-{day}")
    for day in (9, 19, 29):  # abandoned: expensive, no close, never returns
        _ep(msgs, ground, day, 21, f"draft a partnership deck for prospect {day}",
            ["add the audience numbers", "restructure the whole thing",
             "this still is not working at all"], f"abandon-{day}", close=False)

    return sorted(msgs, key=lambda m: m.ts), ground


def main() -> None:
    msgs, ground = build()
    (EX / "prompt_history_gdg.jsonl").write_text(
        "\n".join(json.dumps(m.model_dump(mode="json")) for m in msgs) + "\n")
    (EX / "gdg_ground_truth.json").write_text(json.dumps(ground, indent=1))
    # Tool library (declarations only — name + capability tag).
    tools_dir = EX / "gdg_tools"
    tools_dir.mkdir(exist_ok=True)
    for name, cap in [("calendar_api", "events"), ("outreach_email", "speakers"),
                      ("sponsor_crm", "sponsors")]:
        (tools_dir / f"{name}.yaml").write_text(
            f'ref: tools/{name}\nkind: tool\npayload: \'{{"name": "{name}", "capability": "{cap}"}}\'\n')
    from cle.detect.episodes import DetectorConfig, segment
    episodes = segment(msgs, DetectorConfig())
    print(f"wrote prompt_history_gdg.jsonl: {len(msgs)} messages, {len(episodes)} episodes, {DAYS} days")
    print(f"wrote gdg_ground_truth.json: {len(ground['labeled_threads'])} labeled threads")
    counts = {}
    for v in ground["labeled_threads"].values():
        counts[v] = counts.get(v, 0) + 1
    print("labels:", counts)


if __name__ == "__main__":
    main()
