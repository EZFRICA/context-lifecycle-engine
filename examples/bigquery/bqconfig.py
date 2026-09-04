"""Project, dataset and connection — from the environment, with NO default.

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
    """A required BigQuery identifier is not set. Loud on purpose — see module docstring."""


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


def connection() -> str:
    """Backtick-quoted `project.region.connection` for REMOTE MODEL statements."""
    return f"`{project()}.{_require('CLE_BQ_REGION')}.{_require('CLE_BQ_CONNECTION')}`"
