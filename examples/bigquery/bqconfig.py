"""Project, dataset and connection - from the environment, with NO default.

A project id is not a credential, but it names live infrastructure and these
scripts ship in a public repository, so nothing here is hardcoded.

NO DEFAULT, deliberately. This is the `CLE_STATE_DIR` family: a configuration
that looks like it exists and does not is worse than an absence: a variable that
looks like it redirects and does not is how a run writes into the wrong place. A
silent fallback here would point a query at whatever project the caller happened
to be authenticated against.

    export CLE_BQ_PROJECT=your-project
    export CLE_BQ_DATASET=your-dataset        # the corpus dataset
    export CLE_BQ_CONNECTION=your-connection  # EU CLOUD_RESOURCE connection
"""
import os

from dotenv import load_dotenv

# Load `.env` here rather than requiring an export in every shell, which is what
# the documentation already promises. Reading `os.environ` raw made that promise
# false: the four variables sat in `.env` and no script ever read the file, so
# every one of them raised `MissingBigQueryConfigError` outside a shell that had
# exported them by hand. Loading is idempotent and never overrides an
# already-set variable, so an explicit export still wins.
load_dotenv()


class MissingBigQueryConfigError(RuntimeError):
    """A required BigQuery identifier is not set. Loud on purpose - see module docstring."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingBigQueryConfigError(
            f"{name} is not set. Export it; there is no default, because a default "
            "here would silently address someone else's project."
        )
    return value


def project() -> str:
    return _require("CLE_BQ_PROJECT")


def dataset() -> str:
    """Fully qualified `project.dataset` for the corpus tables."""
    return f"{project()}.{_require('CLE_BQ_DATASET')}"


class _Deferred:
    """A value built on first use, not at import.

    Every bench module used to build its BigQuery client at module scope, so
    IMPORTING one - for a pure helper, a constant, or an AST check - called
    `google.auth.default()` and required `CLE_BQ_*`. A module that cannot be
    imported without credentials cannot be reused or tested offline. The client
    and the dataset name are now built the first time something reads them.

    Supports what the benches do with the two values: attribute access on the
    client (`c.query(...)`) and interpolation of the dataset (`f"{P}.table"`).
    """

    def __init__(self, build):
        self._build = build
        self._value = None

    def resolve(self):
        if self._value is None:
            self._value = self._build()
        return self._value

    def __getattr__(self, name: str):
        # Private names never trigger a build: copy and pickle probe them, and
        # resolving on `_value` itself would recurse.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.resolve(), name)

    def __format__(self, spec: str) -> str:
        return format(self.resolve(), spec)

    def __str__(self) -> str:
        return str(self.resolve())


def lazy_client() -> "_Deferred":
    """The BigQuery client for `project()`, built on first use."""
    def build():
        from google.cloud import bigquery

        return bigquery.Client(project=project())

    return _Deferred(build)


def lazy_dataset() -> "_Deferred":
    """`dataset()`, resolved on first use so a missing variable raises when a
    query needs it rather than when a module is imported."""
    return _Deferred(dataset)


def connection() -> str:
    """Backtick-quoted `project.region.connection` for REMOTE MODEL statements."""
    return f"`{project()}.{_require('CLE_BQ_REGION')}.{_require('CLE_BQ_CONNECTION')}`"
