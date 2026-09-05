"""The dashboard's only write path — Approve / Decline, through the CLI.

Approve promotes a candidate to `trial` (`cle tag <agent> trial`); Decline
records a refusal (`cle decline <agent>`). Both shell out to the same `cle`
binary a human would use, tagged `actor=human:dashboard`, so every write is
logged and auditable. The dashboard never touches the store directly.
"""

import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import Any


def _cle_bin() -> str:
    found = shutil.which("cle")
    if found:
        return found
    candidate = Path(sys.executable).parent / "cle"  # same venv as the server
    return str(candidate)


async def _run(argv: list[str], state_dir: Path) -> dict[str, Any]:
    env = {**os.environ, "CLE_ACTOR": "dashboard"}  # -> actor "human:dashboard"
    argv = argv + ["--state-dir", str(state_dir)]
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(Path.cwd()),
    )
    out, err = await proc.communicate()
    return {
        "argv": argv,
        "code": proc.returncode,
        "stdout": out.decode("utf-8", "replace"),
        "stderr": err.decode("utf-8", "replace"),
    }


async def approve(agent: str, state_dir: Path) -> dict[str, Any]:
    """Human accepts the proposal: candidate -> trial (rides pre_evidence)."""
    return await _run([_cle_bin(), "tag", agent, "trial"], state_dir)


async def decline(agent: str, reason: str | None, state_dir: Path) -> dict[str, Any]:
    """Human refuses the proposal: logged, no tag moved."""
    argv = [_cle_bin(), "decline", agent]
    if reason:
        argv += ["--reason", reason]
    return await _run(argv, state_dir)


async def init_system(state_dir: Path) -> dict[str, Any]:
    """Generate fixtures and build the initial candidate agent."""
    await _run([sys.executable, "examples/make_fixture.py"], state_dir)
    return await _run([
        _cle_bin(), "build", "examples/weekly_recap_agent.yaml",
        "--replay-window", "35d",
        "--history", "examples/prompt_history_adversarial.jsonl"
    ], state_dir)


def demo_run_refusal(state_dir: Path) -> str | None:
    """Why the demo run cannot execute here, or None if it can.

    One predicate, two callers: `run_workspaces` refuses with it, and `/health`
    publishes it so the page can grey the button out BEFORE anyone clicks. That
    is the point of extracting it — an operator should not have to press a button
    to be told it was never going to work, and two copies of the same rule drift
    until the panel and the page disagree about what is possible.
    """
    if state_dir.name == ".cle":
        return (
            f"This dashboard is running on {state_dir}, the live state.\n\n"
            "full_loop.sh begins by deleting the state directory it is given, and "
            "it refuses to do that to `.cle`: that directory holds the only copy "
            "of your oplog, store and topology history, it is gitignored, so git "
            "cannot restore it, and a demo is not a reason to lose it.\n\n"
            "Relaunch the dashboard on a scratch state to use this button:\n"
            "  uv run cle dashboard --state-dir .cle-demo --port 8000\n\n"
            "Your `.cle` is untouched."
        )
    return None


def demo_run_env(state_dir: Path) -> dict[str, Any]:
    """The environment `full_loop.sh` needs, or a refusal explaining why not.

    Returns either `{"env": {...}}` or a ready-made action result with a non-zero
    code. Separated from the running so the endpoint can refuse BEFORE starting a
    background task, and so the refusal reads the same whether it came from the
    button or from `/health`.

    `state_dir` reaches the script as CLE_DEMO_STATE, and that is why the board
    moves while it runs. Every other action here appends `--state-dir`; this one
    used to accept the parameter and ignore it, so the script wrote to its own
    default (`.cle-demo`) while the dashboard tailed the oplog under
    `$CLE_STATE_DIR`. Nothing failed — the script exited 0, wrote its 52 oplog
    lines, and the operator watched a board that never moved.
    """
    blocked = demo_run_refusal(state_dir)
    if blocked:
        return {"argv": [], "code": 1, "stdout": "", "stderr": blocked}

    from dotenv import load_dotenv
    load_dotenv()  # ensure .env is loaded into os.environ for this process

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {
            "argv": [],
            "code": 1,
            "stdout": "",
            "stderr": (
                "GEMINI_API_KEY is not set. Set it in your .env file and restart "
                "the dashboard, or export it before launching.\n"
                "Get a key at https://aistudio.google.com/app/apikey"
            ),
        }

    # CLE_FORCE_REAL_MODEL=1 makes fingerprinter.py raise on any API failure
    # instead of silently falling back to stub hashes, so a green run cannot be
    # an offline run wearing a live label.
    return {"env": {**os.environ, "CLE_FORCE_REAL_MODEL": "1",
                    "CLE_ACTOR": "dashboard", "CLE_DEMO_STATE": str(state_dir)}}


async def clean_system(state_dir: Path) -> dict[str, Any]:
    """Clean persistent state directory.

    `--yes` is required, not a shortcut: this is a subprocess with no tty, so
    `cle clean`'s confirmation prompt would raise rather than ask. The
    confirmation therefore happens where the human actually is, in the browser
    — see `reinitSystem` in dashboard/frontend/app.js.
    """
    return await _run([_cle_bin(), "clean", "--yes"], state_dir)
