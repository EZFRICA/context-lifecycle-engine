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


async def run_workspaces(state_dir: Path) -> dict[str, Any]:
    """Execute the full demo loop script bash examples/full_loop.sh.

    Forces real Gemini model usage: validates GEMINI_API_KEY is present and
    injects CLE_FORCE_REAL_MODEL=1 so fingerprinter.py raises immediately on
    any API failure instead of silently falling back to stub hashes.
    """
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

    force_env = {**os.environ, "CLE_FORCE_REAL_MODEL": "1"}
    proc = await asyncio.create_subprocess_exec(
        "bash", "examples/full_loop.sh",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**force_env, "CLE_ACTOR": "dashboard"},
        cwd=str(Path.cwd()),
    )
    out, err = await proc.communicate()
    return {
        "argv": ["bash", "examples/full_loop.sh"],
        "code": proc.returncode,
        "stdout": out.decode("utf-8", "replace"),
        "stderr": err.decode("utf-8", "replace"),
    }


async def clean_system(state_dir: Path) -> dict[str, Any]:
    """Clean persistent state directory.

    `--yes` is required, not a shortcut: this is a subprocess with no tty, so
    `cle clean`'s confirmation prompt would raise rather than ask. The
    confirmation therefore happens where the human actually is, in the browser
    — see `reinitSystem` in dashboard/frontend/app.js.
    """
    return await _run([_cle_bin(), "clean", "--yes"], state_dir)
