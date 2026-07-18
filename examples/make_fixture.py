"""Generate the P1 exit-demo fixture: a synthetic prompt history and the
candidate the DETECTOR (not a human) writes from it.

Deterministic by construction — no randomness, no wall clock — so the
demo's numbers are reproducible. Run from the repo root:

    .venv/bin/python examples/make_fixture.py

Writes examples/prompt_history.jsonl and examples/weekly_recap_agent.yaml.
"""

import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cle.detect.clusters import HashedTokenEmbedder, IntentClusterer
from cle.detect.episodes import DetectorConfig, Message, cold_start_is_over, segment
from cle.detect.signals import detect_signal
from cle.oplog import OpLog

T0 = datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc)
EXAMPLES = Path(__file__).resolve().parent


def synthetic_history() -> list[Message]:
    """35 days of one user's traffic: a weekly recap ritual (the pattern
    worth an agent) drowned in ordinary one-off traffic."""
    messages: list[Message] = []

    def say(day: float, minute: int, text: str, thread: str) -> None:
        messages.append(
            Message(
                user_id="u1",
                ts=T0 + timedelta(days=day, minutes=minute),
                text=text,
                thread_id=thread,
            )
        )

    # The ritual: every Monday, the same recap request, always taking a
    # couple of clarifying iterations before a thanks.
    for week in range(5):
        day = 7 * week
        thread = f"recap-w{week}"
        say(day, 0, "write the weekly recap of my project for the team", thread)
        say(day, 4, "add the deployment status and the open blockers", thread)
        say(day, 9, "tighten the summary section", thread)
        say(day, 12, "thanks", thread)

    # Ordinary traffic: varied intents, no shared ritual, spread across
    # the same window so out-of-cluster replay has real material.
    noise = [
        (1, "debug the kubernetes ingress timeout on staging", "noise-a"),
        (2, "draft a polite reply to the vendor invoice email", "noise-b"),
        (5, "explain the difference between tokio tasks and threads", "noise-c"),
        (9, "summarize this research paper on retrieval ranking", "noise-d"),
        (11, "fix the flaky integration test in the payments repo", "noise-e"),
        (16, "plan a three day hiking trip near lyon", "noise-f"),
        (18, "review my sql migration for the orders table", "noise-g"),
        (23, "convert this bash script to python", "noise-h"),
        (25, "what changed in the new postgres release", "noise-i"),
        (30, "outline a talk about incident postmortems", "noise-j"),
        (32, "regex to extract iso dates from logs", "noise-k"),
        (3, "rename the feature flag service safely", "noise-l"),
        (8, "compare grafana and datadog pricing tiers", "noise-m"),
        (13, "write a dockerfile for the ml scoring job", "noise-n"),
        (20, "how do i rotate the gcp service account keys", "noise-o"),
        (27, "suggest onboarding exercises for a junior dev", "noise-p"),
        (33, "draft the q3 roadmap one pager", "noise-q"),
        # Boundary traffic: shares some vocabulary with the ritual (team,
        # project, write) without being it — kept below the clustering
        # similarity threshold so it stays out-of-cluster, where the
        # false-trigger rate is measured.
        (10, "summarize monthly metrics for the data team", "noise-r"),
        (24, "write meeting notes for the project sync", "noise-s"),
    ]
    for day, text, thread in noise:
        say(day, 30, text, thread)
        say(day, 34, "thanks", thread)

    return sorted(messages, key=lambda m: m.ts)


def main() -> None:
    config = DetectorConfig()
    messages = synthetic_history()

    history_path = EXAMPLES / "prompt_history.jsonl"
    history_path.write_text(
        "\n".join(json.dumps(m.model_dump(mode="json")) for m in messages) + "\n"
    )

    # Run the detector the way the pipeline would: segment, gate on cold
    # start, cluster, then look for a signal per cluster.
    episodes = segment(messages, config)
    oplog = OpLog(io.StringIO())
    now = messages[-1].ts
    assert cold_start_is_over(messages, episodes, now, config, oplog, actor="human:fixture"), (
        "fixture must clear the cold-start gate"
    )

    clusterer = IntentClusterer(HashedTokenEmbedder(), config)
    assignments = [clusterer.assign(episode) for episode in episodes]
    by_cluster: dict[int, list] = {}
    for episode, cluster_id in zip(episodes, assignments):
        by_cluster.setdefault(cluster_id, []).append(episode)

    candidates = []
    for cluster_id, cluster_episodes in by_cluster.items():
        signal = detect_signal(cluster_episodes, user_baseline=None, config=config)
        if signal is not None:
            candidates.append((cluster_id, cluster_episodes, signal))

    assert candidates, "the ritual cluster must produce a signal"
    # Strongest signal = most occurrences; deterministic tie-break on id.
    cluster_id, cluster_episodes, signal = max(
        candidates, key=lambda item: (item[2].occurrences, -item[0])
    )
    centroid = clusterer.centroids[cluster_id]

    candidate_yaml = {
        "name": "weekly_recap",
        "detected_from": {
            "signal": signal.kind,
            "occurrences": signal.occurrences,
            "episodes": len(cluster_episodes),
        },
        "components": ["#blocks/recap_format", "#blocks/team_context"],
        "trigger": {
            "centroid": [round(v, 6) for v in centroid],
            **(
                {
                    "period": {
                        "interval": signal.period.interval.total_seconds(),
                        "tolerance": signal.period.tolerance,
                    }
                }
                if signal.period
                else {}
            ),
        },
    }
    candidate_path = EXAMPLES / "weekly_recap_agent.yaml"
    candidate_path.write_text(yaml.safe_dump(candidate_yaml, sort_keys=False))
    print(f"wrote {history_path.name}: {len(messages)} messages, {len(episodes)} episodes")
    print(
        f"wrote {candidate_path.name}: cluster {cluster_id}, signal {signal.kind} "
        f"x{signal.occurrences}"
    )


if __name__ == "__main__":
    main()
