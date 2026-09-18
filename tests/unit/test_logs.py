"""The logging configuration (`cle/logs.py`): where diagnostics go, and what never does.

SCOPE: bucket 1 (embedder-agnostic). Nothing here embeds a text.

Three properties, each one a way a usual logging setup would fail here:

  * a diagnostic goes to stderr, because stdout is what scripts and tests read;
  * nothing is written to disk unless a file is named;
  * no user text reaches a log line - a probe is logged by its position, a
    generator failure by its exception type.
"""

import io
import logging
import logging.handlers
import subprocess
import sys
from pathlib import Path

import pytest

from cle import logs
from cle.logs import LOG_FORMAT, ColoredFormatter, configure_logging, get_logger

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def reconfigure(monkeypatch):
    """Reconfigure under a test's environment; the default comes back afterwards."""
    for name in ("CLE_LOG_LEVEL", "CLE_LOG_FILE", "NO_COLOR"):
        monkeypatch.delenv(name, raising=False)

    def apply(**env: str) -> None:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        configure_logging(force=True)

    yield apply
    monkeypatch.undo()
    configure_logging(force=True)


def _ours() -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if getattr(h, "cle_owned", False)]


def test_a_warning_goes_to_stderr_and_never_to_stdout(reconfigure, capsys) -> None:
    reconfigure()
    get_logger("cle.test").warning("the disk is slow")
    out, err = capsys.readouterr()
    assert "the disk is slow" not in out
    assert "| WARNING  | cle.test | the disk is slow" in err


def test_info_is_silent_by_default_and_shown_on_request(reconfigure, capsys) -> None:
    """A normal run prints what it printed before logging existed."""
    reconfigure()
    get_logger("cle.test").info("step one")
    assert "step one" not in capsys.readouterr().err

    reconfigure(CLE_LOG_LEVEL="INFO")
    get_logger("cle.test").info("step two")
    assert "step two" in capsys.readouterr().err


def test_an_unreadable_level_falls_back_to_warning_and_says_so(reconfigure, capsys) -> None:
    reconfigure(CLE_LOG_LEVEL="LOUD")
    assert logging.getLogger().level == logging.WARNING
    assert "CLE_LOG_LEVEL=LOUD is not a level name" in capsys.readouterr().err


def test_nothing_is_written_to_disk_unless_a_file_is_named(reconfigure, tmp_path,
                                                            monkeypatch) -> None:
    """A log file opened in the working directory on import would land in the
    repository, and in every test's cwd."""
    monkeypatch.chdir(tmp_path)
    reconfigure()
    get_logger("cle.test").error("an error")
    assert list(tmp_path.iterdir()) == []


def test_the_named_file_gets_every_line_without_colour(reconfigure, tmp_path) -> None:
    target = tmp_path / "cle.log"
    reconfigure(CLE_LOG_FILE=str(target))
    get_logger("cle.test").warning("written down")
    for handler in _ours():
        handler.flush()
    text = target.read_text()
    assert "| WARNING  | cle.test | written down" in text
    assert "\033[" not in text


def test_the_named_file_rotates_rather_than_growing_without_bound(reconfigure, tmp_path,
                                                                  monkeypatch) -> None:
    """A run left with CLE_LOG_FILE set must not be able to fill the disk."""
    monkeypatch.setattr(logs, "LOG_FILE_MAX_BYTES", 512)
    target = tmp_path / "cle.log"
    reconfigure(CLE_LOG_FILE=str(target))
    for index in range(40):
        get_logger("cle.test").warning("line %d", index)
    for handler in _ours():
        handler.flush()
    assert (tmp_path / "cle.log.1").exists()
    assert target.stat().st_size <= 512 + 128  # the last line may cross the bound


def test_an_unopenable_file_degrades_to_stderr_rather_than_failing(reconfigure, tmp_path,
                                                                   capsys) -> None:
    """A bad path is a misconfiguration, not a reason for a command to die."""
    reconfigure(CLE_LOG_FILE=str(tmp_path / "no" / "such" / "dir" / "cle.log"))
    assert "cannot be opened" in capsys.readouterr().err
    assert len(_ours()) == 1


def test_colour_is_added_to_the_line_and_never_to_the_record() -> None:
    """Rewriting `record.levelname` would hand the colour codes to the file handler."""
    record = logging.LogRecord("cle.x", logging.ERROR, __file__, 1, "boom", None, None)
    coloured = ColoredFormatter(LOG_FORMAT).format(record)
    assert "\033[91mERROR\033[0m" in coloured
    assert record.levelname == "ERROR"
    assert "\033[" not in logging.Formatter(LOG_FORMAT).format(record)


def test_colour_follows_the_stream_at_the_moment_a_line_is_written(reconfigure,
                                                                   monkeypatch) -> None:
    """Deciding once, at configuration time, colours whatever replaced the stream after."""
    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    reconfigure()                       # configured while stderr is pytest's capture
    monkeypatch.setattr(sys, "stderr", Terminal())
    get_logger("cle.test").warning("on a terminal")
    assert "\033[93mWARNING" in sys.stderr.getvalue()

    monkeypatch.setattr(sys, "stderr", io.StringIO())   # a pipe, not a terminal
    get_logger("cle.test").warning("into a pipe")
    assert "\033[" not in sys.stderr.getvalue()


def test_a_formatter_set_on_the_handler_is_used_rather_than_ignored(reconfigure) -> None:
    """Colour is chosen per line, and that choice must not swallow a caller's
    formatter: a silent no-op is what the old `stream` setter did."""
    reconfigure()
    handler = _ours()[0]
    handler.setFormatter(logging.Formatter("PLAIN %(message)s"))
    try:
        record = logging.LogRecord("cle.x", logging.ERROR, __file__, 1, "boom", None, None)
        assert handler.format(record) == "PLAIN boom"
    finally:
        handler.setFormatter(None)


def test_importing_the_engine_touches_nobody_elses_logging() -> None:
    """A library configures nothing: `import cle.x` inside another program must
    not move that program's root level, nor add a handler to its root logger.

    In a subprocess because the assertion is about the state of the root logger
    at import, and this process imported `cle` long ago.
    """
    script = (
        "import logging\n"
        "logging.getLogger().setLevel(logging.DEBUG)\n"
        "import cle.cli.main, cle.detect.embedders, cle.population.generator\n"
        "print(len(logging.getLogger().handlers), logging.getLevelName(logging.getLogger().level))"
    )
    proc = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.split() == ["0", "DEBUG"]


def test_the_cli_configures_logging_and_a_normal_command_stays_silent(tmp_path,
                                                                      monkeypatch) -> None:
    """Two properties in one run, because they are the same run.

    The entry point is what configures - nothing else does it for the CLI - and
    a command that works writes NOTHING to stderr, so a script reading a CLE
    command's output sees exactly what it saw before this module existed.

    The environment is cleared first, and that is not tidiness: this test read
    the ambient one, so it passed offline and failed inside a live run that had
    exported `CLE_LOG_FILE` - where a second handler is CORRECT and the
    assertion was wrong. A property about the default configuration has to name
    the default.
    """
    from typer.testing import CliRunner

    from cle.cli.main import app

    for name in ("CLE_LOG_LEVEL", "CLE_LOG_FILE"):
        monkeypatch.delenv(name, raising=False)
    for handler in _ours():
        logging.getLogger().removeHandler(handler)
    result = CliRunner().invoke(app, ["ps", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert len(_ours()) == 1
    assert result.stderr == ""
    configure_logging(force=True)


def test_reconfiguring_never_stacks_handlers(reconfigure) -> None:
    reconfigure()
    reconfigure()
    get_logger("cle.again")
    assert len(_ours()) == 1


def test_a_logger_keeps_its_full_dotted_name() -> None:
    """A last-segment name would let two modules named `main` share one logger."""
    assert get_logger("cle.build.fingerprinter").name == "cle.build.fingerprinter"


def test_a_failed_probe_is_logged_by_position_never_by_text(reconfigure, capsys,
                                                             monkeypatch) -> None:
    from cle.build.fingerprinter import LiveModelFingerprinter

    class Unreachable:
        def invoke(self, prompt):
            raise ConnectionError("network down")

    monkeypatch.delenv("CLE_FORCE_REAL_MODEL", raising=False)
    reconfigure()
    fingerprinter = object.__new__(LiveModelFingerprinter)
    fingerprinter.model = Unreachable()
    hashes = fingerprinter.outputs(["tickets for Dupont about invoice 4821", "second"])

    err = capsys.readouterr().err
    assert len(hashes) == 2
    assert "probe 1 of 2 failed (ConnectionError)" in err
    assert "Dupont" not in err and "invoice" not in err


def test_a_generator_error_is_logged_by_type_never_by_content(reconfigure, capsys) -> None:
    from cle.population.generator import facet_at_birth

    class Leaky:
        generator_id = "test:leaky"

        def generate(self, sources):
            raise ValueError("could not summarise: tickets for Dupont")

    reconfigure()
    outcome = facet_at_birth(Leaky(), ["tickets for Dupont"])
    err = capsys.readouterr().err
    assert outcome.failure == "generator_error"
    assert "facet generation failed at birth (ValueError)" in err
    assert "Dupont" not in err


def test_a_rate_limited_retry_is_logged(reconfigure, capsys, monkeypatch) -> None:
    """A run that slows down for minutes with nothing on screen reads as a hang."""
    from cle.detect import embedders

    monkeypatch.setattr(embedders.time, "sleep", lambda _seconds: None)
    calls = iter([Exception("429 Too Many Requests"), "vector"])

    def call():
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result

    reconfigure()
    assert embedders.call_with_backoff(call) == "vector"
    assert "rate limited (Exception); retry 1 of" in capsys.readouterr().err
