"""The level 2 board's two scripts: their refusals, pinned.

SCOPE: bucket 1 (embedder-agnostic). Both refusals fire before any vector space,
any BigQuery call or any file read.

`dashboard_level_2/` is part of the repository; these import it plainly, so a
checkout without it fails collection loudly instead of quietly changing the
suite's size.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
for extra in (ROOT / "dashboard_level_2", ROOT / "examples" / "bigquery", ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import discover_intents  # noqa: E402
import export_real  # noqa: E402


def test_an_unknown_view_name_is_refused_before_anything_bills(monkeypatch) -> None:
    """A typo must not reach the loop, where it would print "skipped" and exit 0."""
    monkeypatch.setattr(sys, "argv", ["discover_intents.py", "0.78", "so_veiw"])
    with pytest.raises(SystemExit) as refused:
        discover_intents.main()
    message = str(refused.value)
    assert "so_veiw" in message
    assert all(view in message for view in discover_intents.VIEWS)


def test_the_real_export_refuses_without_its_source_and_writes_nothing(tmp_path,
                                                                        monkeypatch) -> None:
    missing = tmp_path / "facets.parquet"
    monkeypatch.setattr(export_real, "SOURCE", missing)
    monkeypatch.setattr(export_real, "HERE", tmp_path)
    with pytest.raises(SystemExit) as refused:
        export_real.main()
    assert str(missing) in str(refused.value)
    assert not (tmp_path / "data").exists(), "the refusal must come before any write"
