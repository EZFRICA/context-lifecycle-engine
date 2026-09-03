"""Read the corpus parquet artifacts as text — they are not human-readable.

Everything in `examples/bigquery/data/` is columnar binary. This turns it into
something you can open.

    python examples/bigquery/read_data.py                      # what exists
    python examples/bigquery/read_data.py facets_pilot         # schema + first rows
    python examples/bigquery/read_data.py facets_pilot --dump  # full text, to a file

PRIVACY. Several of these files hold real WildChat user prompts — the `episodes`
column of the facet files is raw user text, not summaries. `examples/bigquery/data/`
is gitignored in full, and any dump written by this script lands
there, so it inherits the same rule. Do not move a dump out of that directory.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd

#: numpy arrays are NOT list/tuple — a plain isinstance check prints the array's
#: repr instead of its items, which is how the first dump came out unreadable.
SEQ = (list, tuple, np.ndarray)

D = Path(__file__).resolve().parent / "data"

#: Columns whose cells are long text or lists of long text — printed as blocks
#: rather than squeezed into a table cell.
TEXT_COLUMNS = {"episodes", "facet", "text", "title", "a", "b", "facet_a", "facet_b",
                "ta", "tb", "dup_title", "orig_title", "title_a", "title_b", "content"}


def catalogue() -> None:
    rows = []
    for path in sorted(D.rglob("*.parquet")):
        try:
            frame = pd.read_parquet(path, columns=None)
            rows.append((path.relative_to(D), len(frame), path.stat().st_size / 1e6,
                         ", ".join(frame.columns[:6])))
        except Exception as error:
            rows.append((path.relative_to(D), -1, path.stat().st_size / 1e6,
                         f"illisible: {type(error).__name__}"))
    print(f"{'fichier':46}{'lignes':>10}{'Mo':>8}  colonnes")
    for name, n, mb, cols in rows:
        count = f"{n:,}" if n >= 0 else "?"
        print(f"{str(name):46}{count:>10}{mb:>8.1f}  {cols}")
    print(f"\n{len(rows)} fichiers. Pour en lire un : "
          f"python examples/bigquery/read_data.py <nom sans .parquet>")


def show(stem: str, limit: int, dump: bool, width: int = 100) -> None:
    matches = sorted(D.rglob(f"*{stem}*.parquet"))
    if not matches:
        raise SystemExit(f"aucun fichier ne correspond à {stem!r}")
    path = matches[0]
    if len(matches) > 1:
        print(f"({len(matches)} correspondances, la première : {path.name})\n")
    frame = pd.read_parquet(path)

    print(f"=== {path.relative_to(D)} — {len(frame):,} lignes ===\n")
    print("colonnes :")
    for column in frame.columns:
        sample = frame[column].iloc[0] if len(frame) else None
        kind = type(sample).__name__
        note = f"liste de {len(sample)}" if isinstance(sample, SEQ) else kind
        print(f"  {column:22} {note}")

    out, sink = [], (D / f"{path.stem}.txt" if dump else None)

    def emit(line: str = "") -> None:
        (out.append if dump else print)(line)

    rows = frame if dump else frame.head(limit)
    # Biggest first when there is a size column — that is what one wants to read.
    if "n" in frame.columns:
        rows = rows.sort_values("n", ascending=False)

    emit()
    for i, row in enumerate(rows.itertuples(index=False), 1):
        header = " | ".join(
            f"{c}={getattr(row, c)}" for c in frame.columns
            if c not in TEXT_COLUMNS and not isinstance(getattr(row, c, None), SEQ)
        )
        emit(f"── {i}. {header[:width]}")
        for column in frame.columns:
            if column not in TEXT_COLUMNS:
                continue
            value = getattr(row, column)
            items = list(value) if isinstance(value, SEQ) else [value]
            emit(f"   {column} ({len(items)}) :" if len(items) > 1 else f"   {column} :")
            for item in items:
                for line in textwrap.wrap(str(item).replace("\n", " "), width,
                                          initial_indent="     · ",
                                          subsequent_indent="       ")[:6]:
                    emit(line)
        emit()

    if dump:
        sink.write_text("\n".join(out))
        print(f"\nécrit -> {sink}  ({sink.stat().st_size/1e3:.0f} Ko, {len(frame):,} lignes)")
        print("Ce fichier est dans examples/bigquery/data/, donc gitignoré. "
              "Il peut contenir du texte utilisateur réel — ne pas le déplacer hors de là.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        catalogue()
    else:
        show(args[0], limit=int(args[1]) if len(args) > 1 else 5,
             dump="--dump" in sys.argv)
