"""Central logging: one configuration for the engine, the dashboard and the scripts.

Six choices, each one because the usual alternative breaks something here:

  * STDERR, not stdout. A command's stdout is its product - `full_loop.sh` greps
    `capture_rate` out of `cle build`, the tests read what `cle population`
    prints - so a diagnostic line there would corrupt the thing being read.
  * The stream is resolved when a line is WRITTEN, not when the handler is built.
    A handler built while a test runner had replaced `sys.stderr` would keep
    writing into that runner's buffer after it was closed.
  * THE LIBRARY EMITS, THE APPLICATION CONFIGURES. `get_logger` installs nothing:
    importing `cle.detect.embedders` inside somebody else's program must not move
    their root level or add a handler to their root logger. The four entry points
    that ARE applications call `configure_logging()` themselves:
    `cle/cli/main.py` (the Typer callback), `dashboard/backend/app.py` (the
    lifespan), each script's `main()`, and `tools/mutate.py`. A library module
    that logs with no configuration in place emits nothing, which is the stdlib's
    behaviour and the right one.
  * WARNING by default, `$CLE_LOG_LEVEL` to see more. A normal run prints what it
    printed before this module existed.
  * No file unless `$CLE_LOG_FILE` names one, and that file ROTATES. A file
    opened in the working directory on import lands in the repository and in
    every test's cwd; one that never rotates fills the disk of whoever left
    `CLE_LOG_FILE` set on a long run.
  * The coloured formatter does not rewrite the record. Rewriting
    `record.levelname` would hand the colour codes to every handler that formats
    the record afterwards, the file included. Colour is decided per line, not
    once at configuration time, because the stream at that moment is what says
    whether anything is reading it.

What goes where:

  * OUTPUT - what a command prints for the operator, a bench's table - stays on
    stdout, through `typer.echo` or `print`.
  * DIAGNOSTICS - a retry, a fallback, an error swallowed so the run can go on -
    go through `get_logger(__name__)`.
  * The OPLOG (`cle/oplog.py`) is neither: it is the audit record, one JSON line
    per operation, and nothing here replaces it.

A log line carries no user text: no message, no probe, no facet, no prompt. A log
file outlives the run, and the facet contract keeps user and model prose out of
every record that outlives a build. Log an index, a hash, a kind, an exception's
type.

    CLE_LOG_LEVEL   DEBUG | INFO | WARNING (default) | ERROR | CRITICAL
    CLE_LOG_FILE    a path; every line is also appended there, without colour,
                    rotating at LOG_FILE_MAX_BYTES with LOG_FILE_BACKUPS kept
    NO_COLOR        set to anything to keep colour off a terminal
"""

import logging
import logging.handlers
import os
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%H:%M:%S"

#: The level when `$CLE_LOG_LEVEL` is unset or is not a level name.
DEFAULT_LEVEL = logging.WARNING

#: Rotation for `$CLE_LOG_FILE`: four files of 5 MiB at most, ~20 MiB total.
#: Sized for the run that motivates the file in the first place - a live
#: multi-user run at DEBUG, which is a few MiB - so rotation is a bound on the
#: pathological case, not something a normal diagnostic session hits.
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024
LOG_FILE_BACKUPS = 3

#: Clients that log whole requests at DEBUG and INFO. Held at WARNING, so a
#: diagnostic run shows the engine rather than its HTTP stack - and not the
#: prompts those requests carry.
#:
#: `google_genai` is deliberately ABSENT: it is the one client whose own
#: diagnostics (which model answered, which call was retried) are the thing an
#: operator is watching for during a live run, and it does not log prompt text.
#: Quieting it was tried and removed; the noise is the signal here.
QUIET_LOGGERS = (
    "httpx", "httpcore", "urllib3", "google", "grpc",
    "langchain", "langchain_core", "langchain_google_genai", "openai",
)


def colour_enabled() -> bool:
    """Whether the CURRENT `sys.stderr` should get escape codes.

    Asked per line rather than once: the stream a handler writes to is resolved
    at emit time, so deciding colour at configuration time would colour a file
    or a captured buffer that had replaced a terminal since.
    """
    if os.environ.get("NO_COLOR"):
        return False
    isatty = getattr(sys.stderr, "isatty", None)
    try:
        return bool(isatty and isatty())
    except ValueError:      # a closed stream under a test runner
        return False


class ColoredFormatter(logging.Formatter):
    """Colours the level name in the formatted line, never in the record."""

    COLORS = {
        logging.DEBUG: "\033[90m",       # grey
        logging.INFO: "\033[94m",        # blue
        logging.WARNING: "\033[93m",     # yellow
        logging.ERROR: "\033[91m",       # red
        logging.CRITICAL: "\033[1;91m",  # bold red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        color = self.COLORS.get(record.levelno)
        if color is None:
            return line
        return line.replace(record.levelname, f"{color}{record.levelname}{self.RESET}", 1)


class _StderrHandler(logging.StreamHandler):
    """Writes to whatever `sys.stderr` is at the moment a line is emitted.

    `Handler.__init__` rather than `StreamHandler.__init__`, as the stdlib's own
    `logging._StderrHandler` does: the base constructor assigns `self.stream`,
    and there is nothing to assign to when the stream is a read-only property.
    """

    #: Marks the handlers this module installed, so a reconfiguration removes
    #: them and never pytest's or uvicorn's.
    cle_owned = True

    def __init__(self, level: int = logging.NOTSET) -> None:
        logging.Handler.__init__(self, level)
        self._coloured = ColoredFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        self._plain = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    @property
    def stream(self):  # pyrefly: ignore[bad-override]
        return sys.stderr

    def format(self, record: logging.LogRecord) -> str:
        # An explicitly set formatter WINS. Deciding here is how colour follows
        # the stream, but silently overriding `setFormatter` would be the same
        # kind of quiet no-op as the `stream` setter this class used to carry:
        # the caller's line would vanish and nothing would say why.
        if self.formatter is not None:
            return self.formatter.format(record)
        return (self._coloured if colour_enabled() else self._plain).format(record)


class _FileHandler(logging.handlers.RotatingFileHandler):
    cle_owned = True


def _level_from_env() -> tuple[int, str | None]:
    """The configured level, and the raw value when it named no level."""
    raw = os.environ.get("CLE_LOG_LEVEL", "").strip().upper()
    if not raw:
        return DEFAULT_LEVEL, None
    # The name -> number mapping itself: `getLevelName` also answers a name, but
    # that direction is deprecated, and for an unknown name it returns a string.
    level = logging.getLevelNamesMapping().get(raw)
    return (level, None) if level is not None else (DEFAULT_LEVEL, raw)


def configure_logging(*, force: bool = False) -> None:
    """Install the CLE handlers on the root logger, once per process.

    Called by entry points - a CLI command, the dashboard, a script - and by
    nothing else. Importing a CLE module must leave a host application's logging
    exactly as it found it, so `get_logger` does NOT call this.

    `force` replaces the handlers, which is how a test reconfigures after
    changing the environment. Handlers the CLE did not install are never touched.
    """
    root = logging.getLogger()
    ours = [h for h in root.handlers if getattr(h, "cle_owned", False)]
    if ours and not force:
        return
    for handler in ours:
        root.removeHandler(handler)
        handler.close()

    level, unreadable = _level_from_env()
    root.setLevel(level)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(max(level, logging.WARNING))

    root.addHandler(_StderrHandler())

    log = logging.getLogger(__name__)
    path = os.environ.get("CLE_LOG_FILE", "").strip()
    if path:
        try:
            file_handler = _FileHandler(
                path, mode="a", encoding="utf-8",
                maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUPS,
            )
        except OSError as error:
            log.warning("CLE_LOG_FILE=%s cannot be opened (%s); logging to stderr only",
                        path, type(error).__name__)
        else:
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
            root.addHandler(file_handler)
    if unreadable:
        log.warning("CLE_LOG_LEVEL=%s is not a level name; using WARNING", unreadable)


def get_logger(name: str) -> logging.Logger:
    """A logger for `name`. Installs nothing - see `configure_logging`.

    The full dotted name is kept, not its last segment: two modules both called
    `main` would otherwise share one logger, and a level set on `cle` would no
    longer reach `cle.build.fingerprinter`. The scripts under `examples/` pass a
    short name of their own (`"run_multiuser"`) rather than `__main__`, which
    would be the same name for every one of them.
    """
    return logging.getLogger(name)
