"""Generate a demanding synthetic history that exercises the whole detector,
and let the DETECTOR (not a human) write one candidate per real pattern.

Deterministic by construction — no randomness, no wall clock — so every
number downstream is reproducible. Run from the repo root:

    .venv/bin/python examples/make_fixture.py

What the history contains (≈40 days, one user):
  - weekly_recap    — a weekly ritual        -> RECURRENCE signal
  - standup_digest  — an every-2-days ritual  -> RECURRENCE signal
  - incident_triage — repeated, expensive     -> REFORMULATION signal
  - onboard_setup   — only twice (< 3)         -> NO candidate (below threshold)
  - noise           — varied one-offs + boundary traffic (out-of-cluster)

Because the three ritual clusters have DISTINCT vocabularies, they get
distinct centroids -> distinct probe openers -> distinct fingerprints ->
distinct capture/false-trigger numbers. Two agents that look identical are
a modelling smell, not a feature.

Writes:
  examples/prompt_history.jsonl              (the base window)
  examples/prompt_history_adversarial.jsonl  (adds a bridge -> false trigger)
  examples/<agent>_agent.yaml                (one per detected candidate)
"""

import io
import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cle.detect.clusters import (
    HashedTokenEmbedder,
    IntentClusterer,
    returned_to_cluster,
    user_baseline,
)
from cle.detect.episodes import (
    DetectorConfig,
    Message,
    classify_closure,
    cold_start_is_over,
    segment,
)
from cle.detect.signals import detect_signal
from cle.oplog import OpLog
from cle.store.objects import content_hash

T0 = datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc)
EXAMPLES = Path(__file__).resolve().parent

# A recap rephrasing that still co-clusters with the canonical recap opener
# (cosine ≈ 0.78) but which the hand-authored `status_report` agent owns
# exactly — so at replay the two compete and weekly_recap captures < 100%.
REWORD = "put together the weekly project recap for the team"


@dataclass(frozen=True)
class Cluster:
    """One recurring intent: an opener (with optional reworded variants that
    still co-cluster), N clarifying follow-ups (which set the episode's
    iteration cost), on a period."""

    name: str
    opener: str
    followups: tuple[str, ...]
    period_days: float
    start_day: float
    occurrences: int
    closes_with_thanks: bool
    components: tuple[str, ...] = field(default_factory=tuple)
    # Reworded openers for the LAST k occurrences — same intent, still in the
    # cluster, but lexically distinct enough that an incumbent owning that
    # phrasing steals them at replay (non-trivial capture_rate).
    reworded: tuple[str, ...] = field(default_factory=tuple)

    def opener_for(self, occ: int) -> str:
        first_reworded = self.occurrences - len(self.reworded)
        return self.opener if occ < first_reworded else self.reworded[occ - first_reworded]

    @property
    def detectable(self) -> bool:
        return self.occurrences >= DetectorConfig().min_signal_occurrences


CLUSTERS = [
    Cluster(
        name="weekly_recap",
        opener="write the weekly recap of my project for the team",
        followups=("add the deployment status and the open blockers",
                   "tighten the summary section"),
        period_days=7, start_day=0, occurrences=5, closes_with_thanks=True,
        components=("#blocks/recap_format", "#blocks/team_context"),
        # 2 of 5 weeks the user rephrases toward a "status report" — the
        # status_report incumbent owns that phrasing, so weekly_recap's
        # capture_rate lands below 100% (see REWORD below).
        reworded=(REWORD, REWORD),
    ),
    Cluster(
        name="standup_digest",
        opener="summarize today's standup blockers and progress for engineering",
        followups=("list what each teammate finished yesterday and flag anyone blocked",),
        period_days=2, start_day=1, occurrences=6, closes_with_thanks=True,
        components=("#blocks/standup_format", "#blocks/team_context"),
    ),
    Cluster(
        # Expensive and repeated, closes WITHOUT a marker: the reformulation
        # story — the user keeps hammering the same intent at high cost.
        name="incident_triage",
        opener="diagnose the production latency spike on the checkout service",
        followups=("check the database connection pool saturation",
                   "correlate the error rate with the last deploy",
                   "inspect the slow query log on the orders table",
                   "trace a sample request through the api gateway",
                   "roll back the last config change and compare",
                   "escalate to the platform on-call rotation"),
        period_days=2, start_day=4, occurrences=4, closes_with_thanks=False,
        components=("#blocks/incident_runbook", "#blocks/oncall_context"),
    ),
    Cluster(
        # Only twice — below the recurrence threshold, so the detector must
        # stay SILENT here. Proves detection is evidence-gated, not eager.
        name="onboard_setup",
        opener="draft an onboarding checklist for a new backend engineer",
        followups=("include the repo access and vpn steps",),
        period_days=10, start_day=12, occurrences=2, closes_with_thanks=True,
        components=(),
    ),
]

NOISE = [
    (2, "draft a polite reply to the vendor invoice email"),
    (3, "rename the feature flag service safely"),
    (5, "explain the difference between tokio tasks and threads"),
    (8, "compare grafana and datadog pricing tiers"),
    (11, "plan a three day hiking trip near lyon"),
    (13, "write a dockerfile for the ml scoring job"),
    (17, "regex to extract iso dates from logs"),
    (20, "how do i rotate the gcp service account keys"),
    (24, "convert this bash script to python"),
    (27, "suggest onboarding exercises for a junior dev"),
    (30, "what changed in the new postgres release"),
    (33, "outline a talk about incident postmortems"),
    (36, "review my sql migration for the orders table"),
]


def _episode(messages: list[Message], user: str, start: datetime, texts: list[str], thread: str) -> None:
    for i, text in enumerate(texts):
        messages.append(Message(user_id=user, ts=start + timedelta(minutes=4 * i), text=text, thread_id=thread))


def synthetic_history() -> list[Message]:
    messages: list[Message] = []
    for cluster in CLUSTERS:
        for occ in range(cluster.occurrences):
            start = T0 + timedelta(days=cluster.start_day + cluster.period_days * occ)
            texts = [cluster.opener_for(occ), *cluster.followups]
            if cluster.closes_with_thanks:
                texts = [*texts, "thanks"]
            _episode(messages, "u1", start, texts, f"{cluster.name}-{occ}")
    for day, text in NOISE:
        start = T0 + timedelta(days=day, hours=6)
        _episode(messages, "u1", start, [text, "thanks"], f"noise-{day}")
    return sorted(messages, key=lambda m: m.ts)


def adversarial_history() -> list[Message]:
    """Base history + rejection traps. Two kinds:

    - one BRIDGE episode engineered to fall in a separate cluster yet still
      clear the recap trigger — a genuine false trigger (the rate must not be
      a flat zero);
    - SEVERAL near-but-distinct traps: openers that share vocabulary with a
      detected agent (weekly / recap / standup / diagnose / latency) but a
      different intent, so the agents should NOT fire on them. More traps make
      a harder rejection test than a single bridge.
    """
    messages = list(synthetic_history())
    for i, day in enumerate([9, 23]):
        start = T0 + timedelta(days=day, hours=10)
        _episode(messages, "u1", start,
                 ["review the sales numbers spreadsheet for finance", "thanks"], f"sales-{i}")
    start = T0 + timedelta(days=16, hours=10)
    _episode(messages, "u1", start,
             ["review the weekly recap numbers for the finance team", "thanks"], "bridge")

    # Near-but-distinct traps — same surface vocabulary, DIFFERENT intent, so
    # they must be REJECTED (each sits below the 0.6 trigger similarity). A
    # trap that shares the intent (e.g. "the weekly recap of my book club")
    # would legitimately FIRE — that is the bridge's job above, not a trap's.
    traps = [
        (14, "draft the monthly report for the board of directors"),    # near recap / report
        (21, "review the standup comedy setlist for open mic night"),   # near standup_digest
        (29, "diagnose why my houseplant leaves are turning yellow"),   # near incident / diagnose
        (34, "debug the plot holes in my short story draft"),           # near incident / debug
    ]
    for i, (day, text) in enumerate(traps):
        start = T0 + timedelta(days=day, hours=11)
        _episode(messages, "u1", start, [text, "thanks"], f"trap-{i}")
    return sorted(messages, key=lambda m: m.ts)


def _baseline(clusters_eps: dict[int, list], config: DetectorConfig) -> float:
    """Per-user baseline: median iterations across SUBSTANTIVE clusters
    (>= min occurrences), excluding abandoned closures — the anti-Goodhart
    baseline the reformulation signal is measured against."""
    labelled = []
    for eps in clusters_eps.values():
        if len(eps) < config.min_signal_occurrences:
            continue
        flags = returned_to_cluster(eps, config)
        provisional = statistics.median(e.iterations for e in eps)
        for episode, flag in zip(eps, flags):
            labelled.append((episode, classify_closure(
                episode, returned_to_cluster=flag, user_baseline=provisional, config=config)))
    base = user_baseline(labelled)
    return base if base is not None else 3.0


def _detect(messages: list[Message], config: DetectorConfig):
    episodes = segment(messages, config)
    oplog = OpLog(io.StringIO())
    assert cold_start_is_over(messages, episodes, messages[-1].ts, config, oplog, actor="human:fixture"), \
        "fixture must clear the cold-start gate"
    clusterer = IntentClusterer(HashedTokenEmbedder(), config)
    by_cluster: dict[int, list] = {}
    centroids: dict[int, tuple] = {}
    for episode in episodes:
        cid = clusterer.assign(episode)
        by_cluster.setdefault(cid, []).append(episode)
        centroids[cid] = clusterer.centroids[cid]
    baseline = _baseline(by_cluster, config)
    spec_by_opener = {c.opener: c for c in CLUSTERS}
    detected = []
    for cid, eps in by_cluster.items():
        spec = spec_by_opener.get(eps[0].opener)
        signal = detect_signal(eps, user_baseline=baseline, config=config)
        detected.append((cid, spec, eps, centroids[cid], signal))
    return episodes, baseline, detected


def _write_candidate(spec: Cluster, centroid: tuple, signal) -> Path:
    trigger = {"centroid": [round(v, 6) for v in centroid]}
    if signal.period:
        trigger["period"] = {"interval": signal.period.interval.total_seconds(),
                             "tolerance": signal.period.tolerance}
    doc = {
        "name": spec.name,
        "detected_from": {"signal": signal.kind, "occurrences": signal.occurrences,
                          "episodes": len(spec.followups) and spec.occurrences},
        "components": list(spec.components),
        "trigger": trigger,
    }
    path = EXAMPLES / f"{spec.name}_agent.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return path


def main() -> None:
    config = DetectorConfig()
    messages = synthetic_history()
    (EXAMPLES / "prompt_history.jsonl").write_text(
        "\n".join(json.dumps(m.model_dump(mode="json")) for m in messages) + "\n")

    episodes, baseline, detected = _detect(messages, config)
    print(f"history: {len(messages)} messages, {len(episodes)} episodes, baseline={baseline:.1f} it/ep\n")
    print(f"{'cluster':16} {'signal':13} {'occ':>3}  {'centroid':10}  agent")
    print("-" * 62)
    emitted = 0
    for cid, spec, eps, centroid, signal in sorted(detected, key=lambda d: -len(d[2])):
        name = spec.name if spec else "(noise)"
        fp = content_hash(list(centroid))[:8]
        sig = signal.kind if signal else "—"
        occ = signal.occurrences if signal else len(eps)
        note = ""
        if spec and signal:
            _write_candidate(spec, centroid, signal); emitted += 1
            note = f"-> {spec.name}_agent.yaml"
        elif spec and not signal:
            note = "(below threshold — no candidate)"
        if spec or len(eps) >= 2:
            print(f"{name:16} {sig:13} {occ:>3}  {fp:10}  {note}")

    # Hand-authored incumbent (not detected): it owns the reworded "status
    # report" phrasing exactly. Built BEFORE weekly_recap it competes for the
    # 2 reworded recap episodes, so weekly_recap captures 3/5 = 60% (topology
    # competition, BLUEPRINT §3.2) — a non-trivial capture_rate.
    status_centroid = HashedTokenEmbedder().embed(REWORD)
    (EXAMPLES / "status_report_agent.yaml").write_text(yaml.safe_dump({
        "name": "status_report",
        "detected_from": {"authored": "human", "note": "competes with weekly_recap"},
        "components": ["#blocks/recap_format", "#blocks/team_context"],
        "trigger": {"centroid": [round(v, 6) for v in status_centroid]},
    }, sort_keys=False))
    print("wrote status_report_agent.yaml (hand-authored incumbent for capture competition)")

    adversarial = adversarial_history()
    (EXAMPLES / "prompt_history_adversarial.jsonl").write_text(
        "\n".join(json.dumps(m.model_dump(mode="json")) for m in adversarial) + "\n")
    print(f"\nwrote {emitted} candidate agent(s) + prompt_history[_adversarial].jsonl "
          f"({len(adversarial)} msgs with bridge)")

    # Distinctness guard: no two emitted agents may share a centroid.
    fps = [content_hash(list(c))[:8] for _, spec, _, c, s in detected if spec and s]
    assert len(fps) == len(set(fps)), "emitted agents must have distinct centroids"


if __name__ == "__main__":
    main()
