"""Demo runner — walk the full CLE loop live, one paced step at a time.

Mirrors examples/full_loop.sh as a structured list so the backend can emit
a `demo_step` event (with the zone it affects) before each step and pace
the run so the audience can read the PULSE. Uses the LIVE model path — the
build and the drift revalidation call the real configured LLM (temperature
0 for the fingerprint), so "proof expires" is a genuine substrate change,
not a simulation. Single-flight: a lock prevents two demos at once.
"""

import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

from .oplog_sse import EventBus

# Drift is enacted by revalidating the pinned image against a DIFFERENT real
# model — a true substrate change, not a fake id. Must be a model your key can
# reach (distinct from the build model). Override per venue.
DRIFT_MODEL = os.getenv("CLE_DEMO_DRIFT_MODEL", "gemini-flash-latest")

_PY = sys.executable


def _cle() -> str:
    return shutil.which("cle") or str(Path(sys.executable).parent / "cle")


def _steps(state_dir: Path) -> list[dict[str, Any]]:
    cle, sd = _cle(), ["--state-dir", str(state_dir)]
    win = ["--replay-window", "40d", "--history", "examples/prompt_history_adversarial.jsonl"]
    twelve = ",".join(["success"] * 12)
    return [
        {"title": "Reset state", "zone": "pulse", "argv": [cle, "clean", *sd]},
        {"title": "Detector writes candidates from usage (3 distinct agents)",
         "zone": "births", "argv": [_PY, "examples/make_fixture.py"]},
        {"title": "Build status_report — hand-authored incumbent (owns 'status report')",
         "zone": "births", "argv": [cle, "build", "examples/status_report_agent.yaml", *win, *sd]},
        {"title": "Build weekly_recap — capture 60%: status_report owns 2 of its episodes",
         "zone": "births", "argv": [cle, "build", "examples/weekly_recap_agent.yaml", *win, *sd]},
        {"title": "Build standup_digest — distinct centroid, distinct fingerprint",
         "zone": "births", "argv": [cle, "build", "examples/standup_digest_agent.yaml", *win, *sd]},
        {"title": "Build incident_triage — reformulation-born, expensive",
         "zone": "births", "argv": [cle, "build", "examples/incident_triage_agent.yaml", *win, *sd]},
        {"title": "Run workspace alpha (recap)", "zone": "lives",
         "argv": [cle, "run", "weekly_recap", "--workspace", "alpha", "--prompts", "2", *sd]},
        {"title": "Run workspace beta (incident — divergent metrics)", "zone": "lives",
         "argv": [cle, "run", "incident_triage", "--workspace", "beta", "--prompts", "5", *sd]},
        {"title": "Context-switch cost: alpha recap → incident (real diff)", "zone": "lives",
         "argv": [cle, "run", "incident_triage", "--workspace", "alpha", "--prompts", "1", *sd]},
        {"title": "Human promotes weekly_recap: candidate → trial", "zone": "births",
         "argv": [cle, "tag", "weekly_recap", "trial", *sd]},
        {"title": "Human promotes: trial → ephemeral (lived evidence)", "zone": "lives",
         "argv": [cle, "tag", "weekly_recap", "ephemeral", "--cost-ratio", "0.6",
                  "--occurrences", "4", "--closures", "success,success,success,success", *sd]},
        {"title": "Human pins; shadow engine judges the pin", "zone": "lives",
         "argv": [cle, "tag", "weekly_recap", "pinned", "--cost-ratio", "0.5",
                  "--occurrences", "12", "--closures", twelve, *sd]},
        {"title": "Shadow DIVERGENCE: promote standup on weak evidence; engine would hold",
         "zone": "topology", "argv": [cle, "tag", "standup_digest", "trial", *sd]},
        {"title": "…standup → ephemeral (cost 0.95 > 0.7 threshold)", "zone": "topology",
         "argv": [cle, "tag", "standup_digest", "ephemeral", "--cost-ratio", "0.95",
                  "--occurrences", "3", "--closures", "success,success,reformulated", *sd]},
        {"title": f"Revalidate weekly_recap under a drifted model ({DRIFT_MODEL}) — proof expires",
         "zone": "lives",
         "argv": [cle, "revalidate", "weekly_recap", "--model-id", DRIFT_MODEL, *sd]},
        {"title": "v2 is BORN from the drift — rebuild on the new substrate",
         "zone": "births",
         "argv": [cle, "build", "examples/weekly_recap_agent.yaml", *win,
                  "--model-id", DRIFT_MODEL, *sd]},
    ]


class DemoRunner:
    def __init__(self, bus: EventBus, state_dir: Path) -> None:
        self._bus = bus
        self._state_dir = state_dir
        self._task: asyncio.Task | None = None
        self._abort = asyncio.Event()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, pace_ms: int) -> bool:
        if self.running:
            return False  # single-flight lock
        self._abort.clear()
        self._task = asyncio.create_task(self._run(pace_ms))
        return True

    def abort(self) -> None:
        self._abort.set()

    async def _run(self, pace_ms: int) -> None:
        steps = _steps(self._state_dir)
        total = len(steps)
        pace = max(0.0, pace_ms / 1000.0)
        try:
            for index, step in enumerate(steps, start=1):
                if self._abort.is_set():
                    self._bus.publish({"op": "demo_step", "step": index, "total": total,
                                       "title": "aborted", "zone": "pulse", "state": "aborted"})
                    return
                self._bus.publish({"op": "demo_step", "step": index, "total": total,
                                   "title": step["title"], "zone": step["zone"],
                                   "state": "start"})
                await self._exec(step["argv"])
                # Let the tailer surface the step's oplog lines before pacing on.
                await asyncio.sleep(pace)
            self._bus.publish({"op": "demo_step", "step": total, "total": total,
                               "title": "complete", "zone": "pulse", "state": "done"})
        finally:
            self._task = None

    async def _exec(self, argv: list[str]) -> None:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(Path.cwd()),
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            self._bus.publish({
                "op": "demo_error",
                "argv": argv,
                "stderr": err.decode("utf-8", "replace")[-400:],
            })
