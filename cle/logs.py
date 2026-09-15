"""Central logging: one configuration for the engine, the dashboard and the scripts.

Five choices, each one because the usual alternative breaks something here:

  * STDERR, not stdout. A command's stdout is its product - `full_loop.sh` greps
    `capture_rate` out of `cle build`, the tests read what `cle population`
    prints - so a diagnostic line there would corrupt the thing being read.
  * The stream is resolved when a line is WRITTEN, not when the handler is built.
    A handler built while a test runner had replaced `sys.stderr` would keep
    writing into that runner's buffer after it was closed.
  * WARNING by default, `$CLE_LOG_LEVEL` to see more. A normal run prints what it
    printed before this module existed.
  * No file unless `$CLE_LOG_FILE` names one. A file opened in the working
    directory on import lands in the repository and in every test's cwd.
  * The coloured formatter does not rewrite the record. Rewriting
    `record.levelname` would hand the colour codes to every handler that formats
    the record afterwards, the file included.

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
    CLE_LOG_FILE    a path; every line is also appended there, without colour
    NO_COLOR        set to anything to keep colour off a terminal
"""

import logging
import os
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%H:%M:%S"

#: The level when `$CLE_LOG_LEVEL` is unset or is not a level name.
DEFAULT_LEVEL = logging.WARNING

#: Clients that log whole requests at DEBUG and INFO. Held at WARNING, so a
#: diagnostic run shows the engine rather than its HTTP stack - and not the
#: prompts those requests carry.
QUIET_LOGGERS = (
    "httpx", "httpcore", "urllib3", "google", "grpc",
    "langchain", "langchain_core", "langchain_google_genai", "openai",
)


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
    """Writes to whatever `sys.stderr` is at the moment a line is emitted."""

    #: Marks the handlers this module installed, so a reconfiguration removes
    #: them and never pytest's or uvicorn's.
    cle_owned = True

    @property
    def stream(self):  # pyrefly: ignore[bad-override]
        return sys.stderr

    @stream.setter
    def stream(self, _value) -> None:  # the base class assigns it; the property wins
        pass


class _FileHandler(logging.FileHandler):
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

    `force` replaces them, which is how a test reconfigures after changing the
    environment. Handlers the CLE did not install are never touched.
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

    console = _StderrHandler()
    colour = sys.stderr.isatty() and not os.environ.get("NO_COLOR")
    formatter = ColoredFormatter if colour else logging.Formatter
    console.setFormatter(formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(console)

    log = logging.getLogger(__name__)
    path = os.environ.get("CLE_LOG_FILE", "").strip()
    if path:
        try:
            file_handler = _FileHandler(path, mode="a", encoding="utf-8")
        except OSError as error:
            log.warning("CLE_LOG_FILE=%s cannot be opened (%s); logging to stderr only",
                        path, type(error).__name__)
        else:
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
            root.addHandler(file_handler)
    if unreadable:
        log.warning("CLE_LOG_LEVEL=%s is not a level name; using WARNING", unreadable)


def get_logger(name: str) -> logging.Logger:
    """A logger for module `name`, with the CLE configuration in place.

    The full dotted name is kept, not its last segment: two modules both called
    `main` would otherwise share one logger, and a level set on `cle` would no
    longer reach `cle.build.fingerprinter`.
    """
    configure_logging()
    return logging.getLogger(name)
