## What the numbers are, and are not

**Ground truth by construction.** `examples/make_multiuser.py` partitions the GDG
corpus into 12 synthetic users and every message carries its intent in
`thread_id`. A positive pair is two DIFFERENT users' clusters of the same planted
intent. Nothing was labelled by hand.

**An upper bound, never an estimate.** One generator, so two users sharing an
intent sit closer than two real users would. The inflation is **not uniform**: it
favours the text methods, which share the surface vocabulary a facet abstracts
away.

**The plot is an aid, not evidence.** The scatter is 768 dimensions projected
onto three PCA axes, rotatable with the two sliders. Three axes carry **33% of
the variance on the synthetic corpus and 11% on the real one** - better than two,
and still most of the structure is off screen. Rotate before believing a gap: a
separation that survives every angle means something, one that appears at a
single angle is a fact about the projection. The table is the measurement.

Depth is carried by dot size, nearer being larger, and a small three-axis gnomon
sits in each panel's corner so a rotation reads as a rotation rather than as the
cloud rearranging itself.

The benches behind all of it are `examples/bigquery/facet_crossuser_bench.py`
and `facet_crossuser_so_bench.py`; the figures are published with their pinning
keys in `docs/FINDINGS.md` §6b–§7.
