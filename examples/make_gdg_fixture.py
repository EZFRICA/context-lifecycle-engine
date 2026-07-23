"""GDG organizer fixture — the enriched ground-truth (recovery) source.

FREEZE-ONCE. This script authors realistic, varied usage for one francophone
GDG Cloud Abidjan organiser and freezes it to committed files. Determinism
comes from the COMMITTED .jsonl (like our immutable images), not from a
templated generator: the phrasing is genuinely varied (examples/phrasing.py),
a seeded RNG shapes timing, and the output is written once and reviewed in the
diff. Reproducible on demand, never run in CI.

Cadence is honest (the old fixture scheduled a "monthly" meetup daily): the
window is 16 weeks so a monthly ritual actually recurs monthly, a weekly one
weekly. Tools are declarations only — requires_tool / frozen tool_result
decor, nothing executed.

Outputs:
- prompt_history_gdg.jsonl  — what the detector sees (NO labels).
- gdg_ground_truth.json     — sidecar: planted intents (thread prefix per
  intent, for the realism guard), conflict labels by thread, per-domain tool.
  The detector must never read this.
- gdg_tools/*.yaml          — one declaration per tool.

Run: .venv/bin/python examples/make_gdg_fixture.py
"""

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phrasing as P  # noqa: E402  (pure-data banks, no cle import)

EX = Path(__file__).resolve().parent
T0 = datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc)
WEEKS = 16
DAYS = WEEKS * 7
SEED = 20260401

# Per-domain tool + which planted-intent thread-prefix carries it.
DOMAIN_TOOL = {"events": "calendar_api", "speakers": "outreach_email",
               "sponsors": "sponsor_crm", "newsletter": None,
               "agenda_meetup": None, "agenda_workshop": None, "venue_policy": None}
# The recurring intents the realism guard checks (>= 8 distinct openers each).
PLANTED_INTENTS = list(P.OPENERS.keys())


class Builder:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.msgs: list[dict] = []
        self._hours_used: dict[int, set[int]] = {}
        self.ground: dict = {
            "planted_intents": PLANTED_INTENTS,
            "domain_tool": DOMAIN_TOOL,
            "labeled_threads": {},
            "domains": {}, "patterns": {},
        }
        self._used: dict[str, list[str]] = {}

    def opener(self, intent: str) -> str:
        # Draw openers without repeating until the bank is exhausted, so each
        # planted intent shows its full lexical spread across occurrences.
        pool = self._used.get(intent) or []
        if not pool:
            pool = P.OPENERS[intent][:]
            self.rng.shuffle(pool)
        text = pool.pop()
        self._used[intent] = pool
        return text

    def at(self, day: int, *, spread_hours: tuple[int, int] = (7, 22)) -> datetime:
        # Anchor to midnight so `hour` is the actual hour of day, not an
        # offset from T0's 08:00. Reserve a UNIQUE hour per day so same-day
        # episodes never overlap (each span is < 1h) — overlap would let one
        # thread interleave another and fragment it on thread change.
        midnight = T0.replace(hour=0, minute=0)
        used = self._hours_used.setdefault(day, set())
        choices = [h for h in range(spread_hours[0], spread_hours[1] + 1) if h not in used]
        hour = self.rng.choice(choices) if choices else self.rng.randint(*spread_hours)
        used.add(hour)
        # Start early in the hour so even the longest episode (<= ~40 min)
        # finishes before the next hour slot begins.
        minute = self.rng.randint(0, 12)
        return midnight + timedelta(days=day, hours=hour, minutes=minute)

    def episode(self, intent: str, day: int, thread: str, *, opener: str | None = None,
                followups=(), tool: str | None = None, result: str | None = None,
                label: str | None = None, force_close: bool | None = None,
                spread_hours=(7, 22)) -> None:
        op = opener if opener is not None else self.opener(intent)
        self.msgs += P.assemble_episode(
            self.rng, user_id="gdg", start=self.at(day, spread_hours=spread_hours),
            opener=op, followups=followups, thread_id=thread,
            requires_tool=tool, tool_result=result, force_close=force_close)
        if label:
            self.ground["labeled_threads"][thread] = label

    def some(self, intent: str) -> list[str]:
        # 1–4 varied follow-ups for episode-shape variety (2–5 turns + closer).
        bank = P.FOLLOWUPS.get(intent, [])
        if not bank:
            return []
        k = self.rng.randint(0, min(3, len(bank)))
        return self.rng.sample(bank, k)


def build() -> tuple[list[dict], dict]:
    b = Builder(SEED)
    b.ground["domains"] = {
        "events": {"tool": "calendar_api"}, "speakers": {"tool": "outreach_email"},
        "sponsors": {"tool": "sponsor_crm"}, "community": {"tool": None}}

    # ── events: MONTHLY meetup, each cycle a few scheduling touches ──────────
    # Two of the four monthly cycles are the labeled world_state pairs: same
    # intent, DIFFERENT frozen tool_result across the two touches (world moved).
    world_state_cycles = {1, 3}  # 0-indexed months
    for month in range(4):
        base = month * 28 + b.rng.randint(0, 3)
        touches = 2 if month in world_state_cycles else b.rng.randint(2, 3)
        for t in range(touches):
            day = base + t * b.rng.randint(1, 3)
            if month in world_state_cycles:
                # consistent intent, the world differs between the two touches
                result = "slot_free" if t == 0 else "no_slot"
                follow = [b.rng.choice(P.EVENTS_CONFIRM if result == "slot_free"
                                       else P.EVENTS_REROUTE)]
                b.episode("events", day, f"events-{month}-{t}", followups=follow,
                          tool="calendar_api", result=result, label="world_state")
            else:
                result = b.rng.choice(["slot_free", "no_slot"])
                b.episode("events", day, f"events-{month}-{t}", followups=b.some("events"),
                          tool="calendar_api", result=result)

    # ── newsletter: WEEKLY. Two week-pairs carry the intra_cluster flip ──────
    intra_weeks = {(2, 3), (9, 10)}  # short vs long, close in time
    flip_weeks = {w for pair in intra_weeks for w in pair}
    for week in range(WEEKS):
        day = week * 7 + b.rng.randint(0, 2)
        if week in flip_weeks:
            short = any(week == pair[0] for pair in intra_weeks)
            follow = [b.rng.choice(P.NEWSLETTER_SHORT if short else P.NEWSLETTER_LONG)]
            b.episode("newsletter", day, f"newsletter-{week}", followups=follow,
                      label="intra_cluster")
        else:
            b.episode("newsletter", day, f"newsletter-{week}", followups=b.some("newsletter"))

    # ── speakers: per session, ~biweekly ────────────────────────────────────
    for i, day in enumerate(range(3, DAYS, 12)):
        b.episode("speakers", day + b.rng.randint(0, 2), f"speakers-{i}",
                  followups=b.some("speakers"), tool="outreach_email")

    # ── sponsors: ~weekly follow-ups ────────────────────────────────────────
    for i, day in enumerate(range(5, DAYS, 8)):
        b.episode("sponsors", day + b.rng.randint(0, 2), f"sponsors-{i}",
                  followups=b.some("sponsors"), tool="sponsor_crm")

    # ── routing pair: meetup-night agenda vs coding-workshop agenda ──────────
    # Two near intents recurring on adjacent days — competition, labeled routing.
    # ~12-day cadence so each agenda intent recurs >= 8 times (its full bank).
    for i, day in enumerate(range(10, DAYS, 12)):
        b.episode("agenda_meetup", day, f"agenda_meetup-{i}",
                  followups=b.some("agenda_meetup"), label="routing")
        b.episode("agenda_workshop", day + 1, f"agenda_workshop-{i}",
                  followups=b.some("agenda_workshop"), label="routing")

    # ── temporal: venue policy evolves (DIY early -> ask-approval late) ──────
    for i, day in enumerate((6, 12, 18, 24)):
        b.episode("venue_policy", day, f"venue_policy-{i}",
                  followups=[b.rng.choice(P.VENUE_DIY)], label="temporal")
    for i, day in enumerate((84, 92, 100, 108), start=4):
        b.episode("venue_policy", day, f"venue_policy-{i}",
                  followups=[b.rng.choice(P.VENUE_ASK)], label="temporal")

    # ── community Q&A: frequent, diverse, no tool, no recurrence ─────────────
    for day in range(DAYS):
        for slot in range(b.rng.randint(0, 2)):
            q = b.rng.choice(P.QA_OPENERS)
            b.episode("qa", day, f"qa-{day}-{slot}", opener=q,
                      followups=[], spread_hours=(9, 23))

    # ── noise + abandoned (expensive, no closer, never returns) ──────────────
    for day in range(0, DAYS, 3):
        b.episode("noise", day, f"noise-{day}", opener=b.rng.choice(P.NOISE),
                  followups=[], force_close=b.rng.random() < 0.5)
    for i, day in enumerate((14, 40, 70, 96)):
        b.episode("sponsors", day, f"abandon-{i}",
                  opener=b.rng.choice(P.OPENERS["sponsors"]),
                  followups=b.rng.sample(P.FOLLOWUPS["sponsors"], 2) + ["this still isnt right"],
                  tool="sponsor_crm", force_close=False)

    # ── interruption: a thread stops mid-task, resumes days later (new id) ───
    b.episode("speakers", 22, "speakers-int-a", followups=b.some("speakers"),
              tool="outreach_email", force_close=False)
    b.episode("speakers", 26, "speakers-int-b", followups=b.some("speakers"),
              tool="outreach_email")

    b.ground["patterns"] = {
        "newsletter": {"expected": "unstable_no_candidate"},
        "venue_policy": {"expected": "candidate_from_recent"},
        "routing_pair": {"intents": ["agenda_meetup", "agenda_workshop"]},
    }
    msgs = sorted(b.msgs, key=lambda m: m["ts"])
    return msgs, b.ground


def main() -> None:
    msgs, ground = build()
    (EX / "prompt_history_gdg.jsonl").write_text(
        "\n".join(json.dumps(m) for m in msgs) + "\n")
    (EX / "gdg_ground_truth.json").write_text(json.dumps(ground, indent=1))
    tools_dir = EX / "gdg_tools"
    tools_dir.mkdir(exist_ok=True)
    for name, cap in [("calendar_api", "events"), ("outreach_email", "speakers"),
                      ("sponsor_crm", "sponsors")]:
        (tools_dir / f"{name}.yaml").write_text(
            f'ref: tools/{name}\nkind: tool\npayload: \'{{"name": "{name}", "capability": "{cap}"}}\'\n')

    # Self-report (uses cle — generator only, never CI): how much of the
    # planted structure the v1 detector actually recovers.
    from cle.detect.clusters import HashedTokenEmbedder, IntentClusterer
    from cle.detect.episodes import DetectorConfig, Message, segment
    cfg = DetectorConfig()
    messages = [Message.model_validate(m) for m in msgs]
    episodes = segment(messages, cfg)
    print(f"wrote prompt_history_gdg.jsonl: {len(msgs)} messages, {len(episodes)} episodes, {DAYS} days")
    counts: dict[str, int] = {}
    for v in ground["labeled_threads"].values():
        counts[v] = counts.get(v, 0) + 1
    print("labels:", counts)
    # planted-intent recovery: for each planted intent, how many detected
    # clusters do its openers land in? (1 = clean recovery; >1 = fragmented)
    cl = IntentClusterer(HashedTokenEmbedder(), cfg)
    assign = [(e.messages[0].thread_id.split("-", 1)[0], cl.assign(e), e.opener)
              for e in episodes]
    print(f"detected clusters total: {len(cl.centroids)}")
    for intent in PLANTED_INTENTS:
        rows = [(cid, op) for pfx, cid, op in assign if pfx == intent]
        cids = {cid for cid, _ in rows}
        openers = {op for _, op in rows}
        print(f"  {intent:16} occurrences={len(rows):>2} distinct_openers={len(openers):>2}  "
              f"detected_clusters={len(cids)}")


if __name__ == "__main__":
    main()
