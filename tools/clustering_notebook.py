"""Level 1 clustering, made visible: one corpus, one space, one threshold at a time.

A marimo notebook rather than a script, because the thing worth seeing here is not
a number but a DEPENDENCE: the same openers, in the same space, group differently
at every threshold, and the threshold that is right for one space is wrong for the
next (`CLUSTER_THRESHOLD_BY_EMBEDDER`). A printed table states that; a slider lets
you watch a cluster split.

    uv run --with marimo --with altair marimo edit tools/clustering_notebook.py
    uv run --with marimo --with altair marimo export html tools/clustering_notebook.py -o /tmp/c.html

THE GROUPING IS THE ENGINE'S. Every cluster shown comes from
`cle.population.grouping.group`, the function `cle population` runs, over vectors
from the engine's own embedders. Nothing here reimplements clustering, so what you
see is what the engine does - the failure mode of a notebook that "visualises" a
pipeline by approximating it is that it then disagrees with it silently.

THREE SPACES, and one of them has to be fetched:

  * `stub:hashed64` - the deterministic bag-of-tokens embedder, free, offline.
  * `google:gemini-embedding-2:768` - served from the committed cache
    (`examples/vectors.google-gemini-embedding-2-768.json`), so no key and no spend.
  * `onnx:embeddinggemma-300m-*` - a local ONNX file, free to run, absent unless
    `$CLE_ONNX_MODEL_DIR` points at a directory holding it. See
    `examples/onnx_embedding_bench.py`, which is also where this notebook gets its
    corpora, its labels and its metrics from - one source for both.

WHAT THE PLOT IS NOT. The scatter is 768 dimensions projected onto two PCA axes:
a gap that appears at one projection is a fact about the projection. The variance
kept is printed on the panel, the metrics are computed in the FULL space, and the
table below is the measurement.
"""

import marimo

__generated_with = "0.9.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import pathlib
    import sys

    import altair as alt
    import marimo as mo
    import numpy as np
    import pandas as pd

    ROOT = pathlib.Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "examples"))

    from cle.detect.clusters import CLUSTER_THRESHOLD_BY_EMBEDDER
    from cle.population.grouping import Precomputed, group

    # The bench owns the corpora, the labels and the metrics; importing them keeps
    # the notebook and the published figures on one definition.
    from onnx_embedding_bench import (
        PROMPT_TEMPLATES,
        openers_with_intents,
        purity_completeness,
    )

    return (
        CLUSTER_THRESHOLD_BY_EMBEDDER,
        PROMPT_TEMPLATES,
        Precomputed,
        ROOT,
        alt,
        group,
        mo,
        np,
        openers_with_intents,
        pd,
        purity_completeness,
    )


@app.cell
def _(mo):
    mo.md(
        """
        # Level 1 clustering

        Episode openers, embedded, then grouped by the engine's own `group()`.
        The threshold is **a property of the space**, never a constant: watch the
        cluster count and the two scores move in opposite directions.

        *Trigger detection only — nothing here is about answer quality.*
        """
    )
    return


@app.cell
def _(PROMPT_TEMPLATES, mo, os_environ_model_dir):
    corpus = mo.ui.dropdown(
        options=["holdout", "gdg"], value="holdout", label="corpus",
    )
    spaces = ["stub:hashed64", "google:gemini-embedding-2:768"]
    if os_environ_model_dir:
        spaces.append("onnx:embeddinggemma-300m")
    space = mo.ui.dropdown(options=spaces, value=spaces[1], label="space")
    template = mo.ui.dropdown(
        options=sorted(PROMPT_TEMPLATES), value="query", label="prefix",
    )
    threshold = mo.ui.slider(
        start=0.30, stop=0.98, step=0.01, value=0.70, label="threshold", show_value=True,
    )
    mo.hstack([corpus, space, template, threshold], justify="start", gap=1.2, wrap=True)
    return corpus, space, template, threshold


@app.cell
def _():
    import os

    #: Absent by default: the ONNX space is a 622 MB download this notebook does
    #: not perform. With it unset, the space simply does not appear in the picker.
    os_environ_model_dir = os.environ.get("CLE_ONNX_MODEL_DIR", "")
    return os, os_environ_model_dir


@app.cell
def _(corpus, openers_with_intents):
    pairs = openers_with_intents(corpus.value)
    texts = [t for t, _ in pairs]
    intents = [i for _, i in pairs]
    return intents, pairs, texts


@app.cell
def _(os_environ_model_dir, space, template, texts):
    import pathlib as _pathlib

    def _vectors(space_id: str) -> tuple[dict, str]:
        """text -> unit vector, plus the full space id that produced it."""
        if space_id == "stub:hashed64":
            from cle.detect.embedders import open_embedder

            embedder = open_embedder("stub")
            return ({t: tuple(embedder.embed(t)) for t in dict.fromkeys(texts)},
                    embedder.embedder_id)
        if space_id.startswith("google:"):
            from cle.detect.embedders import CachedEmbedder

            cached = CachedEmbedder.from_file()
            held = {}
            for t in dict.fromkeys(texts):
                try:
                    held[t] = tuple(cached.embed(t))
                except Exception:
                    pass        # an opener the paid cache does not hold; counted below
            return held, cached.embedder_id
        from onnx_embedding_bench import OnnxEmbedder

        onnx = OnnxEmbedder(_pathlib.Path(os_environ_model_dir), "fp16", template.value)
        return onnx.embed_all(texts), onnx.embedder_id

    vectors, space_id = _vectors(space.value)
    covered = [t for t in texts if t in vectors]
    return covered, space_id, vectors


@app.cell
def _(
    CLUSTER_THRESHOLD_BY_EMBEDDER,
    Precomputed,
    covered,
    group,
    intents,
    pd,
    purity_completeness,
    space_id,
    texts,
    vectors,
):
    SWEEP_GRID = [round(0.30 + 0.02 * i, 2) for i in range(35)]
    held_intents = [i for t, i in zip(texts, intents) if t in vectors]
    space_obj = Precomputed(vectors, space_id)

    rows = []
    for _t in SWEEP_GRID:
        assigned = group(list(covered), space_obj, _t)
        purity, completeness = purity_completeness(assigned, held_intents)
        f = 2 * purity * completeness / (purity + completeness) if purity + completeness else 0.0
        rows.append({"threshold": _t, "clusters": len(set(assigned)),
                     "purity": purity, "completeness": completeness, "F": f})
    sweep_frame = pd.DataFrame(rows)
    calibrated = CLUSTER_THRESHOLD_BY_EMBEDDER.get(space_id)
    return SWEEP_GRID, assigned, calibrated, held_intents, purity, rows, space_obj, sweep_frame


@app.cell
def _(covered, group, held_intents, purity_completeness, space_obj, threshold):
    current = group(list(covered), space_obj, threshold.value)
    cur_purity, cur_completeness = purity_completeness(current, held_intents)
    cur_f = (2 * cur_purity * cur_completeness / (cur_purity + cur_completeness)
             if cur_purity + cur_completeness else 0.0)
    singletons = sum(1 for c in set(current) if list(current).count(c) == 1)
    return cur_completeness, cur_f, cur_purity, current, singletons


@app.cell
def _(covered, cur_completeness, cur_f, cur_purity, current, mo, singletons, space_id, texts):
    def _tile(label, value, note=""):
        return (f"<div style='padding:10px 14px;border:1px solid #2a333c;border-radius:10px;"
                f"background:#171d23;min-width:120px'>"
                f"<div style='font:12px ui-monospace;letter-spacing:.14em;text-transform:uppercase;"
                f"color:#8a97a3'>{label}</div>"
                f"<div style='font:22px ui-monospace;color:#dce3e8;margin-top:2px'>{value}</div>"
                f"<div style='font:11px ui-monospace;color:#6b7784'>{note}</div></div>")

    mo.Html(
        "<div style='display:flex;gap:10px;flex-wrap:wrap'>"
        + _tile("clusters", len(set(current)), f"{singletons} singleton(s)")
        + _tile("purity", f"{cur_purity:.0%}")
        + _tile("completeness", f"{cur_completeness:.0%}")
        + _tile("F", f"{cur_f:.3f}")
        + _tile("openers", f"{len(covered)}",
                f"of {len(texts)} in {space_id.split(':')[0]}")
        + "</div>"
    )
    return


@app.cell
def _(alt, calibrated, mo, space_id, sweep_frame, threshold):
    SURFACE = "#171d23"
    INK, MUTED, FAINT = "#dce3e8", "#8a97a3", "#6b7784"
    #: The CLE accents, darkened into the dark-mode lightness band and ordered so
    #: amber and coral are never adjacent. Validated with the six colour checks
    #: (lightness band, chroma floor, CVD separation, normal-vision floor,
    #: contrast): all pass on this surface.
    SERIES = ["#3f86c4", "#b8832b", "#2f9a7c", "#c8503a", "#7d68d8"]

    def themed(chart, height=260, width=560):
        # An explicit width, because altair's default is ~200px: the first
        # export came out with the legend reading "completenes".
        return (chart.properties(height=height, width=width, background=SURFACE)
                .configure_view(stroke="#2a333c")
                .configure_axis(domainColor="#2a333c", gridColor="#1c2530", tickColor="#2a333c",
                                labelColor=MUTED, titleColor=MUTED,
                                labelFont="ui-monospace", titleFont="ui-monospace",
                                labelFontSize=11, titleFontSize=11)
                # Legend BELOW, not beside: to the right it needs horizontal room
                # the notebook column does not always have, and the first export
                # dropped it off the panel entirely on a narrow window. A legend
                # that disappears when the window narrows is identity carried by
                # colour alone.
                .configure_legend(labelColor=INK, titleColor=MUTED, labelFont="ui-monospace",
                                  titleFont="ui-monospace", labelFontSize=11, titleFontSize=11,
                                  orient="bottom", direction="horizontal", titleAnchor="start")
                .configure_title(color=INK, font="ui-monospace", fontSize=12, anchor="start"))

    long = sweep_frame.melt("threshold", ["purity", "completeness", "F"],
                            var_name="measure", value_name="value")
    # One axis: all three measures live in [0, 1]. A second scale for the cluster
    # count would be a dual axis, which is the one chart shape this never uses.
    lines = (alt.Chart(long)
             .mark_line(strokeWidth=2, interpolate="monotone")
             .encode(
                 x=alt.X("threshold:Q", title="threshold",
                         scale=alt.Scale(domain=[0.30, 0.98], nice=False)),
                 y=alt.Y("value:Q", title="score", scale=alt.Scale(domain=[0, 1])),
                 color=alt.Color("measure:N", title=None,
                                 scale=alt.Scale(domain=["purity", "completeness", "F"],
                                                 range=[SERIES[0], SERIES[1], SERIES[2]])),
                 tooltip=[alt.Tooltip("threshold:Q", format=".2f"),
                          alt.Tooltip("measure:N"), alt.Tooltip("value:Q", format=".3f")]))
    here = (alt.Chart(sweep_frame.assign(at=threshold.value))
            .mark_rule(strokeWidth=1.5, color=INK, strokeDash=[2, 2]).encode(x="at:Q"))
    marks = [lines, here]
    if calibrated:
        marks.append(alt.Chart(sweep_frame.assign(cal=calibrated))
                     .mark_rule(strokeWidth=1.5, color=SERIES[1], strokeDash=[6, 3])
                     .encode(x="cal:Q"))
    mo.vstack([
        mo.md(f"**Threshold sweep** — {space_id}"
              + (f" · dashed amber = the {calibrated} this space ships"
                 if calibrated else " · this space ships no calibrated threshold")),
        themed(alt.layer(*marks).resolve_scale(x="shared")),
    ])
    return INK, MUTED, SERIES, SURFACE, themed


@app.cell
def _(SERIES, alt, covered, current, held_intents, mo, np, pd, themed, vectors):
    matrix = np.array([vectors[t] for t in covered])
    centred = matrix - matrix.mean(axis=0)
    _, singular, components = np.linalg.svd(centred, full_matrices=False)
    xy = centred @ components[:2].T
    kept = float((singular[:2] ** 2).sum() / (singular ** 2).sum())

    # Colour carries the PLANTED intent, which is identity and has at most five
    # values here. Cluster membership is in the tooltip, not in a sixth hue: a
    # corpus can produce seventy clusters, and seventy generated hues would be
    # decoration rather than encoding.
    top = [i for i, _ in pd.Series(held_intents).value_counts().items()][:5]
    shown_intents = [i if i in top else "other" for i in held_intents]
    # "other" enters the legend only when something was actually folded into it:
    # a legend entry with no mark is a category the reader goes looking for.
    domain = top + (["other"] if "other" in shown_intents else [])
    frame = pd.DataFrame({
        "x": xy[:, 0], "y": xy[:, 1],
        "intent": shown_intents,
        "cluster": [str(c) for c in current],
        "opener": [t[:70] + ("…" if len(t) > 70 else "") for t in covered],
    })
    scatter = (alt.Chart(frame)
               .mark_circle(size=90, opacity=0.9, stroke= "#171d23", strokeWidth=2)
               .encode(
                   x=alt.X("x:Q", title=f"PC1", axis=alt.Axis(labels=False, ticks=False)),
                   y=alt.Y("y:Q", title="PC2", axis=alt.Axis(labels=False, ticks=False)),
                   color=alt.Color("intent:N", title="planted intent",
                                   scale=alt.Scale(domain=domain,
                                                   range=(SERIES[:len(top)]
                                                          + (["#8a97a3"] if "other" in domain
                                                             else [])))),
                   tooltip=["intent:N", "cluster:N", "opener:N"]))
    mo.vstack([
        mo.md(f"**Openers projected on two PCA axes** — {kept:.0%} of the variance kept, "
              "so believe the table over the gaps. Colour is the planted intent; "
              "the cluster the engine assigned is in the tooltip."),
        themed(scatter, height=320),
    ])
    return domain, frame, kept, matrix, scatter, shown_intents, top, xy


@app.cell
def _(SERIES, alt, current, mo, pd, themed):
    sizes = (pd.Series(current).value_counts().rename_axis("cluster")
             .reset_index(name="openers").astype({"cluster": str}))
    bars = (alt.Chart(sizes)
            .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=SERIES[0])
            .encode(
                x=alt.X("cluster:N", sort="-y", title="cluster at the current threshold"),
                y=alt.Y("openers:Q", title="openers"),
                tooltip=["cluster:N", "openers:Q"]))
    mo.vstack([mo.md("**Cluster sizes** — a long tail of singletons is over-splitting; "
                     "one tall bar is the collapse."),
               themed(bars, height=200)])
    return bars, sizes


@app.cell
def _(frame, mo, sweep_frame):
    mo.ui.tabs({
        "sweep (the measurement)": mo.ui.table(sweep_frame.round(3), selection=None),
        "openers": mo.ui.table(frame.drop(columns=["x", "y"]), selection=None),
    })
    return


if __name__ == "__main__":
    app.run()
