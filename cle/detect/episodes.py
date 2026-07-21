"""Episode segmentation — silence threshold + explicit markers (v1, no BOCPD).

Contract (replay-validation skill, BLUEPRINT §9 decision 1 as settled in the
approved P1 plan):
- Split on silence > 2x the user's median inter-message gap, floor 30 min;
  under 20 recorded gaps the threshold sits on the floor. Explicit markers
  ("thanks", new-thread) split unconditionally.
- Closure classification feeds the anti-Goodhart guard: abandoned episodes
  are EXCLUDED from cost baselines (part 7).
- Cold start: <14 days of history or <20 episodes => no candidates; the
  detector observes silently and logs {"op":"detector_observing",...}.

PROVISIONAL — closure completion. The skill's two labels are contradictory
on the no-marker cells (success is "explicit marker / no return" while
abandoned is "no marker AND no return to cluster": a silent non-returning
episode satisfies both). Completion implemented here, pending maintainer
adjudication:
- explicit marker                                  -> success
- no marker, returned to cluster in window         -> reformulated
  (a failed attempt the user retried; legitimate lived cost, and the raw
  material of the reformulation signal)
- no marker, no return, cost <= 1.5x user baseline -> success
  (satisfied silence)
- no marker, no return, cost  > 1.5x user baseline -> abandoned
  (struggled, then vanished; excluded from baselines so quick abandonment
  can never be gamed into looking cheap)
"""

import re
import statistics
from datetime import datetime, timedelta
from typing import Literal, Sequence

from pydantic import BaseModel, Field

from cle.oplog import OpLog

Closure = Literal["success", "reformulated", "abandoned"]


class DetectorConfig(BaseModel, frozen=True):
    """Detector thresholds — config with article defaults; the cost knobs
    are RELATIVE to the per-user baseline, never absolute."""

    silence_floor: timedelta = timedelta(minutes=30)
    silence_multiplier: float = 2.0
    # Below this many recorded gaps the threshold sits on the floor: a
    # sparse history yields a meaningless median.
    min_gaps_for_median: int = 20
    success_markers: tuple[str, ...] = ("thanks", "thank you", "merci")
    # An episode whose cluster sees the user again within this window was
    # a failed attempt (reformulation), not a closure.
    reformulation_window: timedelta = timedelta(hours=72)
    reformulation_cost_multiplier: float = 1.5
    # Cold start (replay-validation skill): observe silently below these.
    min_history: timedelta = timedelta(days=14)
    min_episodes: int = 20
    # Clustering: minimum cosine similarity between an opener embedding
    # and a centroid to join the cluster rather than found a new one.
    cluster_similarity_threshold: float = 0.6
    # Signals (replay-validation skill): >=3 occurrences for either
    # signal; a period is "stable" when the coefficient of variation of
    # the inter-arrival times stays within this tolerance.
    min_signal_occurrences: int = 3
    recurrence_tolerance: float = 0.25


class Message(BaseModel, frozen=True):
    """One user prompt, as the detector sees history: who, when, what."""

    user_id: str
    ts: datetime
    text: str
    thread_id: str | None = None
    # Capability decor (CLE need: a candidate can match an intent yet lack
    # the capability the task requires — capability-aware triggering needs
    # the episode to declare it). Optional; absent in tool-less domains.
    requires_tool: str | None = None
    # FROZEN environmental result (e.g. "no_slot"). The system may READ it
    # to classify divergence (world-state vs user contradiction); no code
    # path ever executes a tool or asserts this value correct — tool
    # output is answer-quality territory, which replay never validates
    # (invariant 5).
    tool_result: str | None = None


class Episode(BaseModel, frozen=True):
    """A contiguous stretch of one user's messages pursuing one intent."""

    user_id: str
    messages: tuple[Message, ...] = Field(min_length=1)
    ended_with_marker: bool

    @property
    def opener(self) -> str:
        # The opener is what gets embedded for intent clustering.
        return self.messages[0].text

    @property
    def started_at(self) -> datetime:
        return self.messages[0].ts

    @property
    def ended_at(self) -> datetime:
        return self.messages[-1].ts

    @property
    def iterations(self) -> int:
        # Cost unit of v1: how many prompts the intent took (BLUEPRINT §3's
        # historical_cost is the mean of this over a cluster).
        return len(self.messages)

    @property
    def required_tool(self) -> str | None:
        # The capability this episode's task needed (first declared).
        return next((m.requires_tool for m in self.messages if m.requires_tool), None)

    @property
    def tool_results(self) -> tuple[str, ...]:
        # Frozen environmental decor, in order — readable, never asserted.
        return tuple(m.tool_result for m in self.messages if m.tool_result)


def silence_threshold(gaps: Sequence[timedelta], config: DetectorConfig) -> timedelta:
    """Decision 1: 2x the user's median gap, floor 30 min.

    Median, not mean — overnight and weekend gaps are outliers, not
    rhythm. Sparse histories (<20 gaps) sit on the floor rather than
    trusting a meaningless median.
    """
    if len(gaps) < config.min_gaps_for_median:
        return config.silence_floor
    return max(config.silence_multiplier * statistics.median(gaps), config.silence_floor)


def _contains_success_marker(text: str, config: DetectorConfig) -> bool:
    # Word-boundary match: "thanksgiving" is not a closure. A stray split
    # would deflate iterations and with it historical_cost.
    lowered = text.lower()
    return any(
        re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in config.success_markers
    )


def segment(messages: Sequence[Message], config: DetectorConfig) -> list[Episode]:
    """Split one user's chronological history into episodes.

    Split points: silence beyond the threshold, a thread change, or the
    previous message carrying a success marker (markers close an episode,
    so the split lands after them). Single-user, sorted input is a
    precondition, not a repair we attempt.
    """
    if not messages:
        return []
    if any(m.user_id != messages[0].user_id for m in messages):
        raise ValueError("segment() expects one user's history; got mixed user_ids")
    timestamps = [m.ts for m in messages]
    if timestamps != sorted(timestamps):
        raise ValueError("segment() expects chronologically sorted messages")

    gaps = [later - earlier for earlier, later in zip(timestamps, timestamps[1:])]
    threshold = silence_threshold(gaps, config)

    episodes: list[Episode] = []
    current: list[Message] = [messages[0]]
    for previous, message in zip(messages, messages[1:]):
        silence_split = (message.ts - previous.ts) > threshold
        thread_split = message.thread_id != previous.thread_id
        marker_split = _contains_success_marker(previous.text, config)
        if silence_split or thread_split or marker_split:
            episodes.append(_close(current, config))
            current = [message]
        else:
            current.append(message)
    episodes.append(_close(current, config))
    return episodes


def _close(messages: list[Message], config: DetectorConfig) -> Episode:
    return Episode(
        user_id=messages[0].user_id,
        messages=tuple(messages),
        ended_with_marker=_contains_success_marker(messages[-1].text, config),
    )


def classify_closure(
    episode: Episode,
    *,
    returned_to_cluster: bool,
    user_baseline: float,
    config: DetectorConfig,
) -> Closure:
    """Label how an episode ended — see the PROVISIONAL note in the module
    docstring for the completion this implements.

    `returned_to_cluster` is cluster knowledge (did the same user open
    another episode in the same cluster within the reformulation window?)
    computed by the caller; `user_baseline` is yesterday's baseline —
    using today's would be circular, since baselines exclude the abandoned
    episodes this function identifies.
    """
    if episode.ended_with_marker:
        return "success"
    if returned_to_cluster:
        return "reformulated"
    if episode.iterations <= config.reformulation_cost_multiplier * user_baseline:
        return "success"
    return "abandoned"


def cold_start_is_over(
    messages: Sequence[Message],
    episodes: Sequence[Episode],
    now: datetime,
    config: DetectorConfig,
    oplog: OpLog,
    *,
    actor: str,
) -> bool:
    """Gate candidate detection on history depth (replay-validation skill).

    Under 14 days of history or 20 episodes the detector observes
    silently — visible in `cle log` via the detector_observing line.
    """
    history_span = now - messages[0].ts if messages else timedelta(0)
    if history_span >= config.min_history and len(episodes) >= config.min_episodes:
        return True
    oplog.emit(
        "detector_observing",
        actor=actor,
        history_days=round(history_span / timedelta(days=1), 2),
        episodes=len(episodes),
    )
    return False
