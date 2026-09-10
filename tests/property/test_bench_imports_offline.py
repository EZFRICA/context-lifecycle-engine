"""Every module under `examples/bigquery` imports offline and touches nothing.

SCOPE: bucket 1 (embedder-agnostic). Nothing here embeds, queries or bills.

A bench module that did its work at import could not be imported to reuse one
of its helpers, to type-check it, or to test it: eleven of them read parquet,
read the BigQuery configuration or ran queries at module scope, and two built a
client whose construction calls `google.auth.default()`. Importing one on a box
without credentials failed, and importing one anywhere ran it.

The check runs in a SEPARATE interpreter, from an empty working directory, with
the Google credential variables removed and HOME pointed at an empty directory,
which is what a CI runner without data or credentials looks like. It fails on a
module that raises at import, and on one that writes into the working directory.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BENCH = ROOT / "examples" / "bigquery"

_IMPORT_ALL = """
import importlib, sys
failed = []
for name in sys.argv[1:]:
    try:
        importlib.import_module(name)
    except BaseException as error:  # SystemExit included: a module may not exit on import
        failed.append(f"{name}: {type(error).__name__}: {error}"[:240])
print("\\n".join(failed))
sys.exit(1 if failed else 0)
"""

_WITHHELD = ("GOOGLE_APPLICATION_CREDENTIALS", "CLOUDSDK_CONFIG", "GEMINI_API_KEY",
             "GOOGLE_API_KEY", "CLE_BQ_PROJECT", "CLE_BQ_DATASET", "CLE_BQ_REGION",
             "CLE_BQ_CONNECTION", "CLE_VERTEX_PROJECT")


def test_every_bench_module_imports_offline_and_writes_nothing(tmp_path) -> None:
    modules = sorted(path.stem for path in BENCH.glob("*.py"))
    assert len(modules) > 20, "the glob no longer finds the bench modules"
    cwd, home = tmp_path / "cwd", tmp_path / "home"
    cwd.mkdir()
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in _WITHHELD}
    env.update(HOME=str(home), PYTHONPATH=os.pathsep.join(map(str, (BENCH, ROOT / "examples", ROOT))))

    result = subprocess.run([sys.executable, "-c", _IMPORT_ALL, *modules], cwd=cwd, env=env,
                            capture_output=True, text=True, timeout=240)

    assert result.returncode == 0, f"not importable offline:\n{result.stdout}\n{result.stderr[-1500:]}"
    assert list(cwd.iterdir()) == [], "a module wrote into the working directory at import"
