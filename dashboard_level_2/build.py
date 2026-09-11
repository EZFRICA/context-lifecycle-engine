"""Build the level 2 board from the exported view.

Reads `data/crossuser_view.json` (written by `export_view.py`) and writes a
single self-contained `index.html`. No server, no build step, no dependency: the
data is embedded, so the file opens from disk and can be handed to someone.

WHAT THE BOARD IS FOR. The CLE's question is not how to create agents - there is
no shortage of those - but whether the agents that already exist still earn their
standing. Level 2 answers that across a population: if one person's agent has a
counterpart in eleven other topologies, it is a shape the population keeps
producing; if it stands alone, its value has to come from somewhere else.

Grouping is therefore the measurement underneath a lifecycle decision, and the
board exists to make the two candidate architectures comparable rather than to
rank them. Both columns are shown side by side, with what each buys and what each
costs, because the constraint that decides between them (may we store user text?)
is the reader's, not ours.
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
DATA = json.loads((HERE / "data" / "crossuser_view.json").read_text(encoding="utf-8"))

#: The real-user view, when it has been exported. It carries no labels, so it
#: contributes the PLOT and the similarity spread, never a recall figure. Absent
#: on a machine without the gitignored WildChat material, and the board then
#: falls back to the synthetic view alone rather than pretending.
_real = HERE / "data" / "real_view.json"
REAL = json.loads(_real.read_text(encoding="utf-8")) if _real.exists() else None

#: Stack Overflow across authors: the only corpus here with real users AND real
#: labels, so it is the one whose recall table means the most. Absent on a
#: machine that has not run the bench.
_so = HERE / "data" / "so_view.json"
SO = json.loads(_so.read_text(encoding="utf-8")) if _so.exists() else None


def _gap(scores: dict | None, text_row: str, budget: str) -> str:
    """How far the facet path sits below the best text path, at one budget.

    COMPUTED, never typed. Three of these were hardcoded once and every one of
    them was wrong by the time anybody read them: the page rendered a table from
    one export while its prose quoted gaps from a superseded one. A figure that
    appears both as prose and as data must be derived from the data, or the two
    drift apart silently and the page argues with itself.

    `scores` is None when the view was never exported (`so_view.json` is absent
    on a machine that has not run the bench), and the page then says so rather
    than printing a number.
    """
    if scores is None:
        return "n/a"
    return f"{scores[text_row][budget] - scores['facet-redacted'][budget]:.1f}"


#: Stack Overflow's best text row is `title-cosine`; the synthetic view calls the
#: same thing `text`. Named here so the gaps below cannot silently compare the
#: wrong pair.
SO_GAP_101 = _gap(SO and SO["scores"], "title-cosine", "0.101")
SO_GAP_01 = _gap(SO and SO["scores"], "title-cosine", "0.01")
GDG_GAP_101 = _gap(DATA["scores"], "text", "0.101")
GDG_GAP_01 = _gap(DATA["scores"], "text", "0.01")

#: The facet-redacted recall the board actually renders for the synthetic view,
#: quoted in prose beside the reproducibility spread so the two cannot disagree.
GDG_FACET_101 = DATA["scores"]["facet-redacted"]["0.101"]
GDG_FACET_01 = DATA["scores"]["facet-redacted"]["0.01"]


def _recall(scores: dict | None, row: str, budget: str) -> str:
    """One recall figure for a headline card, read from the export like the gaps."""
    return "n/a" if scores is None else f"{scores[row][budget]:.1f}%"


#: The two headline cards. They were typed once and one of them (64.9%) outlived
#: the export it came from.
SO_TEXT_101 = _recall(SO and SO["scores"], "title-cosine", "0.101")
SO_FACET_101 = _recall(SO and SO["scores"], "facet-redacted", "0.101")

HEAD = """<meta charset="utf-8">
<title>Level 2 Cluster Board</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
:root{
  --ground:#eef1f4; --surface:#fff; --panel:#f7f9fa; --ink:#131a21; --ink-2:#3d4954;
  --muted:#5f6b78; --rule:#d3d9df; --rule-2:#b6bec6;
  --keep:#1f6fb2; --keep-soft:#dce9f4; --priv:#a75b12; --priv-soft:#f2e4d4;
  --dot:#9aa6b2;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#0f1317; --surface:#161b21; --panel:#1b2128; --ink:#e0e6ec; --ink-2:#b3bcc6;
  --muted:#87929e; --rule:#262e37; --rule-2:#3a444f;
  --keep:#3e8fcc; --keep-soft:#1c2b39; --priv:#c07a28; --priv-soft:#2e2519;
  --dot:#4a5763;
}}
:root[data-theme="dark"]{
  --ground:#0f1317; --surface:#161b21; --panel:#1b2128; --ink:#e0e6ec; --ink-2:#b3bcc6;
  --muted:#87929e; --rule:#262e37; --rule-2:#3a444f;
  --keep:#3e8fcc; --keep-soft:#1c2b39; --priv:#c07a28; --priv-soft:#2e2519;
  --dot:#4a5763;
}
*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);margin:0;padding:0 1.25rem 4rem;
  font-family:Archivo,"Helvetica Neue",Arial,sans-serif;font-size:15px;line-height:1.55;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:78rem;margin:0 auto}
header{border-bottom:2px solid var(--ink);padding:2.5rem 0 1.25rem;margin-bottom:1.5rem}
.eyebrow{font-family:"JetBrains Mono",monospace;font-size:.6875rem;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);display:flex;gap:1.25rem;flex-wrap:wrap;
  margin-bottom:1rem}
h1{font-size:2.25rem;font-weight:700;letter-spacing:-.02em;margin:0 0 .6rem;line-height:1.05}
h2{font-size:1.25rem;font-weight:600;letter-spacing:-.01em;margin:2.5rem 0 .3rem}
.lede{color:var(--ink-2);max-width:64ch;margin:0;font-size:1.0625rem}
.lede b{color:var(--ink)}
.sub{color:var(--muted);max-width:70ch;margin:.3rem 0 1rem;font-size:.9375rem}
.note{background:var(--panel);border:1px solid var(--rule-2);border-left:3px solid var(--priv);
  border-radius:2px;padding:.85rem 1.1rem;margin:1.25rem 0 0;font-size:.8125rem;
  color:var(--ink-2);max-width:70ch}
.note b{color:var(--priv)}

/* the two architectures, at parity */
.arch{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem;margin-top:.5rem}
@media(max-width:820px){.arch{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:2px;padding:1.25rem}
.card.a{border-top:3px solid var(--keep)}
.card.b{border-top:3px solid var(--priv)}
.card h3{margin:0 0 .1rem;font-size:1.0625rem;font-weight:600}
.card .id{font-family:"JetBrains Mono",monospace;font-size:.6875rem;letter-spacing:.08em;
  text-transform:uppercase;margin-bottom:.9rem}
.card.a .id{color:var(--keep)} .card.b .id{color:var(--priv)}
.big{font-family:"JetBrains Mono",monospace;font-size:2rem;font-weight:600;
  font-variant-numeric:tabular-nums;line-height:1;margin-bottom:.15rem}
.card.a .big{color:var(--keep)} .card.b .big{color:var(--priv)}
.big-l{font-size:.75rem;color:var(--muted);margin-bottom:1rem}
.card ul{margin:.2rem 0 1rem;padding-left:1.05rem}
.card li{margin-bottom:.35rem;font-size:.875rem;color:var(--ink-2)}
.card .h{font-family:"JetBrains Mono",monospace;font-size:.625rem;letter-spacing:.12em;
  text-transform:uppercase;color:var(--muted);margin:0 0 .1rem}
.card .stores{border-top:1px solid var(--rule);padding-top:.7rem;font-size:.8125rem;
  color:var(--ink-2)}
.card .stores b{color:var(--ink)}

/* plot */
.controls{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;margin:1.25rem 0 1rem}
.controls .lbl{font-family:"JetBrains Mono",monospace;font-size:.6875rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);margin-right:.5rem}
.chip{font-family:"JetBrains Mono",monospace;font-size:.75rem;padding:.3rem .6rem;
  border:1px solid var(--rule-2);border-radius:99px;background:var(--surface);
  color:var(--ink-2);cursor:pointer}
.chip[aria-pressed="true"]{background:var(--ink);border-color:var(--ink);color:var(--surface)}
.chip:focus-visible{outline:2px solid var(--keep);outline-offset:2px}
/* Two columns, not three. The third panel made every plot 300px wide, which is
   where a 400-point cloud stops being readable; the third method now wraps onto
   its own row at full width. */
.panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1.25rem}
@media(max-width:900px){.panels{grid-template-columns:1fr}}
.panel{background:var(--surface);border:1px solid var(--rule);border-radius:2px;padding:1rem}
.panel h4{font-size:.9375rem;font-weight:600;margin:0 0 .15rem}
.panel .meta{font-family:"JetBrains Mono",monospace;font-size:.6875rem;color:var(--muted);
  margin-bottom:.6rem}
svg{width:100%;height:auto;display:block}
.spin{display:flex;align-items:center;gap:.7rem;margin:.6rem 0 1rem;max-width:34rem}
.spin input{flex:1;accent-color:var(--keep)}
.spin span{font-family:"JetBrains Mono",monospace;font-size:.625rem;color:var(--muted);
  letter-spacing:.1em;text-transform:uppercase}
.grid{stroke:var(--rule);stroke-width:.5;fill:none}
.axes{stroke:var(--rule-2);stroke-width:1;fill:none}
.axis-l{fill:var(--muted);font-family:"JetBrains Mono",monospace;font-size:10px}
.plabel{font-family:"JetBrains Mono",monospace;font-size:9px;fill:var(--ink-2)}
/* Two regimes, and the second is why the real view once looked empty.
   When an intent is selected, unselected dots are CONTEXT and recede. When
   nothing is selected - the real corpus carries no intents - every dot is the
   subject, so it takes the panel's own accent at full strength. Leaving them on
   the muted colour rendered 130 points at roughly 1.3:1 against the panel: drawn,
   and invisible. */
.dot{fill:var(--dot);opacity:.45}
.dot.on{opacity:1}
.panel.k .dot.on{fill:var(--keep)} .panel.p .dot.on{fill:var(--priv)}
/* When nothing is selected every mark IS the subject, so it takes the panel's
   accent at full strength. Leaving them muted once rendered 130 real points at
   about 1.3:1 against the panel: drawn, and invisible. */
.dot.lone{opacity:.8}
.panel.k .dot.lone{fill:var(--keep)}
.panel.p .dot.lone{fill:var(--priv)}
.axes{stroke:var(--rule-2);stroke-width:1;fill:none}
.axis-l{fill:var(--muted);font-family:"JetBrains Mono",monospace;font-size:9px}
.spin{display:flex;align-items:center;gap:.6rem;margin:.4rem 0 0}
.spin input{flex:1;accent-color:var(--keep)}
.spin span{font-family:"JetBrains Mono",monospace;font-size:.625rem;color:var(--muted);
  letter-spacing:.08em;text-transform:uppercase}
.hull{opacity:0;stroke-width:1}
.hull.on{opacity:.5}
.panel.k .hull{fill:var(--keep-soft);stroke:var(--keep)}
.panel.p .hull{fill:var(--priv-soft);stroke:var(--priv)}
.stat{display:flex;gap:1.1rem;flex-wrap:wrap;border-top:1px solid var(--rule);
  margin-top:.7rem;padding-top:.6rem;font-family:"JetBrains Mono",monospace;
  font-size:.6875rem;color:var(--muted)}
.stat b{color:var(--ink);font-weight:600}

table{border-collapse:collapse;width:100%;font-family:"JetBrains Mono",monospace;
  font-size:.8125rem;font-variant-numeric:tabular-nums;margin-top:.5rem}
caption{text-align:left;color:var(--muted);font-family:Archivo,sans-serif;
  font-size:.8125rem;padding-bottom:.5rem}
th,td{text-align:right;padding:.42rem .7rem;border-bottom:1px solid var(--rule);
  white-space:nowrap}
th:first-child,td:first-child{text-align:left;padding-left:0}
thead th{font-size:.6875rem;letter-spacing:.06em;text-transform:uppercase;
  color:var(--muted);border-bottom:1px solid var(--rule-2)}
tr.a td:first-child{border-left:3px solid var(--keep);padding-left:.5rem}
tr.b td:first-child{border-left:3px solid var(--priv);padding-left:.5rem}
.foot{border-top:1px solid var(--rule-2);margin-top:2.5rem;padding-top:1rem;
  font-family:"JetBrains Mono",monospace;font-size:.6875rem;color:var(--muted);
  line-height:1.75}
</style>
"""

TOP = f"""
<div class="wrap">
<header>
  <div class="eyebrow"><span>Context Lifecycle Engine</span><span>Level 2 &middot; population layer</span><span>46 clusters &middot; 12 users &middot; 7 intents</span></div>
  <h1>Level 2 Cluster Board</h1>
  <p class="lede">Agents are cheap to create and expensive to keep. Level 2 asks the
  question that decides whether an existing one still earns its standing:
  <b>does anyone else's usage produce the same shape?</b> An agent whose intent
  recurs across eleven other topologies is a pattern the population keeps making.
  One that stands alone has to justify itself some other way.</p>
  <p class="sub">Grouping is the measurement underneath that decision. Two architectures
  can do it, and they are not ranked here - the constraint that separates them is
  yours.</p>
</header>

<h2>Two architectures, at parity</h2>
<p class="sub">Headline figures come from <b>Stack Overflow across authors</b> - the
only corpus here with real users AND real labels, 3,000 pairs a moderator ruled on. The
synthetic corpus agrees on the ordering and overstates the gap; WildChat has no labels and
cannot rank them at all.</p>
<div class="arch">
  <div class="card a">
    <h3>Read the episodes</h3>
    <div class="id">raw text &middot; embed what people wrote</div>
    <div class="big">{SO_TEXT_101}</div>
    <div class="big-l">recall at a 10.1% false-positive budget, on real labelled pairs
      (90.7% on the synthetic corpus, which flatters it)</div>
    <p class="h">strengths</p>
    <ul>
      <li>The strongest grouping measured here, at every budget.</li>
      <li>No generation step: nothing to prompt, nothing to re-generate, nothing that
          drifts between runs.</li>
      <li>Cheaper per cluster - one embedding call, no LLM call.</li>
      <li>Its failure mode is legible: two clusters are close because their words are.</li>
    </ul>
    <p class="h">weaknesses</p>
    <ul>
      <li>The population layer reads raw user text, which is what the facet contract
          exists to forbid.</li>
      <li>Every privacy question moves to storage and access control, where it is
          harder to check than a generated sentence.</li>
      <li>Part of its lead is an artefact of the synthetic corpus - one generator,
          shared surface vocabulary - but not all: it still leads by {SO_GAP_101} points on
          real Stack Overflow authors who share nothing.</li>
    </ul>
    <p class="stores">Level 2 stores: <b>the episodes themselves</b>.</p>
  </div>
  <div class="card b">
    <h3>Read a generated facet</h3>
    <div class="id">clio layer 1 &middot; one sentence per cluster</div>
    <div class="big">{SO_FACET_101}</div>
    <div class="big-l">recall at the same budget, after mechanical redaction
      (69&ndash;76% on the synthetic corpus, and it moves per run)</div>
    <p class="h">strengths</p>
    <ul>
      <li>No user text is ever stored. The artefact is one generated sentence.</li>
      <li>Mechanical redaction takes proper nouns to <b>0.00</b> per facet and costs
          nothing here - it even helps at the strict budget.</li>
      <li>The privacy property is checkable by a regex, not by a policy.</li>
      <li>Facets are readable: a human can audit what the population layer holds.</li>
    </ul>
    <p class="h">weaknesses</p>
    <ul>
      <li><b>{SO_GAP_101} points below raw text</b> on the real labelled corpus at this budget,
          and {SO_GAP_01} at a 1% budget. The synthetic corpus puts the same gap at
          {GDG_GAP_101} and {GDG_GAP_01}, so the cost depends on how hard the negatives
          are - and synthetic negatives are the easy kind.</li>
      <li><b>Not reproducible run to run.</b> Five generations of the same 46 clusters,
          same corpus and same protocol, gave 75.0 / 76.4 / 71.4 / {GDG_FACET_101} / 74.3
          at this budget and 32.1 / 27.9 / 18.6 / {GDG_FACET_01} / 30.0 at 1%. The fourth
          is the draw this table renders. The embedding rows are identical every time;
          the generation step is the only thing that moves.</li>
      <li>Adds an LLM call per cluster, with its cost and its latency.</li>
      <li>Abstraction is the mechanism and the risk - it removes the detail that
          separates two neighbouring tasks.</li>
    </ul>
    <p class="stores">Level 2 stores: <b>one sentence, 0.00 proper nouns</b>.</p>
  </div>
</div>

<p class="note"><b>The choice is a constraint, not a score.</b> Two labelled corpora, one
synthetic and one real, agree that raw text groups better. If your setting allows the
population layer to hold user text, the left column groups better, costs less to run, and
gives the same answer every time. If it does not - regulation, consent, or a promise
you made - the right column is the only one of the two available at all, and 69&ndash;76%
is what it costs on the synthetic corpus.
<br><br>
Note which column is stable. The text rows reproduce to the decimal across runs; the facet
rows move by up to 13.5 points at the strict budget. A lifecycle decision that retires an
agent should not depend on which draw of a generation it landed on, so a facet deployment
needs its facets frozen once and reused - not regenerated per report.</p>

<h2>Where the clusters land</h2>
<p class="sub">Two corpora, and they answer different questions. <b>Real users</b> show what
level 2 would actually see: 130 clusters from 40 WildChat users, real prompts, real facets,
and no labels. <b>Synthetic users</b> are the only place recall can be measured, because
there a shared intent is known by construction.</p>
<div class="controls" id="sources"><span class="lbl">data</span></div>
<div class="controls" id="chips"><span class="lbl">intent</span></div>
<div class="controls" id="groups"><span class="lbl">discovered group</span></div>
<div class="spin"><span>rotate</span>
  <input id="yaw" type="range" min="0" max="360" value="35" step="1"
         aria-label="rotate the projection around the vertical axis">
  <span>tilt</span>
  <input id="pitch" type="range" min="-80" max="80" value="18" step="1"
         aria-label="tilt the projection">
</div>
<div class="panels" id="panels"></div>
<div id="spread"></div>

<p class="note"><b>Intents on the real corpora are DISCOVERED, not given.</b> Only GDG
carries intents, because a generator planted them. The names on Stack Overflow and
WildChat are the system's own output - facets grouped by the engine's clusterer, then
named by a model. They are hypotheses about what a group has in common, never labels, and
nothing scores a method against them. The threshold was calibrated where the answer IS
known: swept on GDG against its planted intents, 0.78 balances purity 76% against
completeness 80%. Applying that number to corpora whose density nobody has checked is the
weakest link here.
<br><br>
And it shows: at 0.78 Stack Overflow splits into 367 groups with 345 singletons, WildChat
into 116 with 105. Most real cross-user clusters have no counterpart at this scale -
40 users, or 400 questions, is not a population.</p>

<p class="note"><b>Read the plot with suspicion.</b> These are 768-dimension vectors
projected onto three PCA axes, which you can rotate. Three axes carry
<b>33% of the variance on the synthetic corpus and 11% on the real one</b> - better
than two, and still most of the structure is off the screen. Points that look far apart
may not be; points that overlap may not be close. Drag to rotate, scroll to zoom, arrow keys work too; all three panels share one
camera, because three clouds at three angles compare nothing. Rotate before believing a
gap: a cluster that separates from every angle is telling you something, one that
separates from a single angle is telling you about the projection. The table below is the measurement - the
plot only helps you read it.</p>

<h2>What the real corpus shows, without labels</h2>
<p class="sub">Nobody has said which two real users share an intent, so there is no recall
here. What can be measured is how close cross-user clusters get - 8,128 pairs from 40
users.</p>
<table>
  <caption>Cross-user similarity on real WildChat clusters. Higher is not automatically
  better: more pairs above a threshold means more candidates surfaced, not more correct
  ones. <b>The two facet rows are identical because they are the same texts</b>:
  mechanical redaction changed <b>0 of 130</b> WildChat facets, so this corpus measures
  redaction's cost at nothing because it never applied it - a non-measurement, not
  a verdict that redaction is free. On the two labelled corpora it does bite, and the
  rows differ.</caption>
  <thead><tr><th>method</th><th>median</th><th>p99</th><th>pairs &ge; 0.7</th><th>&ge; 0.8</th></tr></thead>
  <tbody id="spreadrows"></tbody>
</table>
<p class="note"><b>Facets surface 7&times; more candidates than raw text here</b> - 135
pairs above 0.7 against 19 - which is the opposite of what the labelled corpus said.
The synthetic bench predicted the direction and understated the size: one generator gives
raw text a shared vocabulary that flatters it, and 40 strangers do not share one.
<br><br>
It does not follow that the 135 are right. Facets are also the method that collapses two
neighbouring tasks into one generic sentence, and over-merging produces this number too.
Telling the two apart needs cross-user ground truth on real users, which does not exist
here. Free word overlap, meanwhile, finds nothing at all: median 0.023, and not one pair
of 8,128 reaches 0.7.</p>

<h2>The measurement, where labels exist</h2>
<p class="sub" id="scorenote"></p>
<table>
  <caption>Recall at a matched false-positive rate - 966 cross-user pairs, 140 of
  them the same intent. The threshold is set on the pairs that do NOT match and read on
  the pairs that do.</caption>
  <thead><tr><th>method</th><th>@10.1% FP</th><th>@5% FP</th><th>@1% FP</th></tr></thead>
  <tbody id="scores"></tbody>
</table>

<p class="note"><b>The ranking changes with the budget.</b> At 10.1% the embedded methods
lead and free word overlap is last. At 1% free word overlap beats everything except raw
text, and beats both facet methods by more than 24 points. Fix the error budget your
lifecycle decision needs before choosing a method - a method chosen at a loose budget
and deployed at a strict one is sometimes the wrong one, not a slightly worse one.</p>

<p class="foot">
Ground truth by construction: <code>make_multiuser.py</code> partitions the GDG corpus
into 12 synthetic users, and every message carries its intent in <code>thread_id</code>.
Nothing was labelled by hand.<br>
UPPER BOUND, not an estimate - one generator, so two users sharing an intent sit
closer than two real users would. The inflation is not uniform: it favours the text
methods, which share the surface vocabulary a facet abstracts away. On real users the gap
should narrow, by an unmeasured amount.<br>
Facet generation is not deterministic at temperature 0, and the spread is not small:
five runs of the same 46 clusters gave 75.0 / 76.4 / 71.4 / {GDG_FACET_101} / 74.3 at the
10.1% budget and 32.1 / 27.9 / 18.6 / {GDG_FACET_01} / 30.0 at 1%. The table shows the
fourth. The text rows are identical across all five.<br>
Rebuild: <code>uv run python dashboard_level_2/export_view.py &amp;&amp; uv run python dashboard_level_2/build.py</code>
</p>
</div>
"""

SCRIPT = """
<script id="data" type="application/json">__DATA__</script>
<script id="real" type="application/json">__REAL__</script>
<script id="so" type="application/json">__SO__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const R = JSON.parse(document.getElementById("real").textContent);
const S = JSON.parse(document.getElementById("so").textContent);
const SOURCES = [].concat(S ? ["so"] : [], R ? ["real"] : [], ["synthetic"]);
const SRC_LABEL = {
  "so":"Stack Overflow, real users + labels",
  "real":"WildChat, real users, no labels",
  "synthetic":"GDG, synthetic users, labelled"};
let source = SOURCES[0];
function view(){ return source === "so" ? S : source === "real" ? R : D; }
function labelled(){ return source !== "real"; }
const ORDER = ["text", "facet", "facet-redacted"];
const LABEL = {"text":"raw episodes","facet":"facet","facet-redacted":"facet, redacted"};
const TONE  = {"text":"k","facet":"p","facet-redacted":"p"};
let active = D.intents[0];
let activeGroup = "";



/* Orthographic projection of the three PCA axes.
   Rotate around the vertical, then tilt. Depth is kept and used for the cue
   below rather than thrown away: without it a third axis is decoration. */
function project3(p){
  const a = yaw * Math.PI / 180, b = pitch * Math.PI / 180;
  const x = p.x * Math.cos(a) + (p.z || 0) * Math.sin(a);
  const zr = -p.x * Math.sin(a) + (p.z || 0) * Math.cos(a);
  const y = p.y * Math.cos(b) - zr * Math.sin(b);
  const depth = p.y * Math.sin(b) + zr * Math.cos(b);
  return [x, y, depth];
}

const sources = document.getElementById("sources");
SOURCES.forEach(function(s){
  const b = document.createElement("button");
  b.className = "chip"; b.type = "button"; b.textContent = SRC_LABEL[s];
  b.dataset.src = s;
  b.onclick = function(){ source = s; render(); };
  sources.appendChild(b);
});

const groupsEl = document.getElementById("groups");
const yawEl = document.getElementById("yaw"), pitchEl = document.getElementById("pitch");
yawEl.oninput = function(){ yaw = +yawEl.value; render(); };
pitchEl.oninput = function(){ pitch = +pitchEl.value; render(); };
const chips = document.getElementById("chips");
D.intents.forEach(function(i){
  const b = document.createElement("button");
  b.className = "chip"; b.type = "button"; b.textContent = i;
  b.onclick = function(){ active = i; render(); };
  chips.appendChild(b);
});

function hull(pts){
  if (pts.length < 3) return "";
  const p = pts.slice().sort(function(a,b){ return a[0]-b[0] || a[1]-b[1]; });
  function cr(o,a,b){ return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0]); }
  const lo = [], up = [];
  p.forEach(function(q){ while(lo.length>=2 && cr(lo[lo.length-2],lo[lo.length-1],q)<=0) lo.pop(); lo.push(q); });
  p.slice().reverse().forEach(function(q){ while(up.length>=2 && cr(up[up.length-2],up[up.length-1],q)<=0) up.pop(); up.push(q); });
  return lo.slice(0,-1).concat(up.slice(0,-1))
    .map(function(c){ return c[0].toFixed(1)+","+c[1].toFixed(1); }).join(" ");
}

/* ── the projection ────────────────────────────────────────────────────────
   Back to hand-drawn SVG after a WebGL detour. Three PCA axes, rotated
   orthographically by two sliders: the third axis is real, the rendering is not
   a black box, and a reader can read the markup. */
const KEY0 = {"so":{"text":"title-cosine","facet":"facet-cosine",
                    "facet-redacted":"facet-redacted"}};
let yaw = 35, pitch = 18;

/* The named groups worth colouring. Capped, because a validated categorical
   palette does not stretch to the 367 groups Stack Overflow found. */
function groupsOf(V){
  const counts = {};
  (V.views.facet ? V.views.facet.points : []).forEach(function(p){
    if (p.discovered) counts[p.discovered] = (counts[p.discovered] || 0) + 1; });
  return Object.keys(counts).sort(function(a,b){ return counts[b]-counts[a]; }).slice(0, 8);
}

/* Rotate around the vertical, then tilt. Depth is returned, not discarded: it
   orders the draw and sizes the mark, which is what makes the third axis do
   any work. */
function project3(p){
  const a = yaw * Math.PI / 180, b = pitch * Math.PI / 180;
  const x  = p.x * Math.cos(a) + (p.z || 0) * Math.sin(a);
  const zr = -p.x * Math.sin(a) + (p.z || 0) * Math.cos(a);
  return [x, p.y * Math.cos(b) - zr * Math.sin(b),
          p.y * Math.sin(b) + zr * Math.cos(b)];
}


function esc(s){ return String(s).replace(/[&<>]/g, function(m){
  return {"&":"&amp;","<":"&lt;",">":"&gt;"}[m]; }); }

function render(){
  Array.prototype.forEach.call(sources.querySelectorAll(".chip"), function(b){
    b.setAttribute("aria-pressed", String(b.dataset.src === source)); });
  // The intent chips only mean anything on the labelled corpus. Real clusters
  // carry no intent, so highlighting by intent is hidden rather than shown
  // pressing nothing.
  chips.style.display = source === "synthetic" ? "" : "none";
  Array.prototype.forEach.call(chips.querySelectorAll(".chip"), function(b){
    b.setAttribute("aria-pressed", String(b.textContent === active)); });

  const V = view();

  // Discovered groups, rebuilt per corpus: they are this corpus's own output,
  // not a fixed vocabulary. "all" clears the selection.
  const names = groupsOf(V);
  groupsEl.innerHTML = '<span class="lbl">discovered group</span>';
  ["all"].concat(names).forEach(function(n){
    const b = document.createElement("button");
    b.className = "chip"; b.type = "button"; b.textContent = n;
    b.setAttribute("aria-pressed", String(n === "all" ? activeGroup === "" : activeGroup === n));
    b.onclick = function(){ activeGroup = (n === "all" ? "" : n); render(); };
    groupsEl.appendChild(b);
  });

  const host = document.getElementById("panels");
  host.className = "panels";
  host.innerHTML = "";
  ORDER.forEach(function(key){
    const v = V.views[key];
    if (!v) return;
    const W = 560, H = 420, PAD = 34;
    function sx(x){ return PAD + (x + 1) / 2 * (W - 2 * PAD); }
    function sy(y){ return PAD + (1 - (y + 1) / 2) * (H - 2 * PAD); }

    // Project, then draw back to front so nearer marks sit on top.
    const placed = v.points.map(function(p){
      const q = project3(p);
      const hit = activeGroup
        ? p.discovered === activeGroup
        : (source === "synthetic" && p.intent === active);
      return {p: p, x: sx(q[0]), y: sy(q[1]), d: q[2], hit: hit};
    }).sort(function(a, b){ return a.d - b.d; });

    const anySelected = placed.some(function(o){ return o.hit; });
    const marks = placed.map(function(o){
      const near = (o.d + 1) / 2;
      const r = (o.hit ? 4.5 : 2.8) + near * 2.4;
      const cls = "dot" + (o.hit ? " on" : (anySelected ? "" : " lone"));
      const who = o.p.user ? o.p.user + " \\u00b7 " : "";
      const what = o.p.discovered || o.p.intent || "ungrouped";
      const tip = who + what + " \\u00b7 " + o.p.n + " cluster" + (o.p.n === 1 ? "" : "s") +
                  (o.p.family_name ? " \\u00b7 family " + o.p.family_name : "");
      return '<circle class="' + cls + '" cx="' + o.x.toFixed(1) + '" cy="' +
             o.y.toFixed(1) + '" r="' + r.toFixed(1) + '"><title>' + esc(tip) +
             '</title></circle>';
    }).join("");

    // A gnomon, so a rotation reads as a rotation.
    const G = 34, gx = W - G - 16, gy = H - G - 16;
    const gnomon = [[1,0,0,"1"],[0,1,0,"2"],[0,0,1,"3"]].map(function(a){
      const q = project3({x:a[0], y:a[1], z:a[2]});
      const ex = gx + q[0]*G, ey = gy - q[1]*G;
      return '<line class="axes" x1="' + gx + '" y1="' + gy + '" x2="' + ex.toFixed(1) +
             '" y2="' + ey.toFixed(1) + '"></line><text class="axis-l" x="' +
             (ex + (q[0] >= 0 ? 4 : -10)).toFixed(1) + '" y="' + (ey + 4).toFixed(1) +
             '">' + a[3] + '</text>';
    }).join("");

    const frame = '<rect class="grid" x="' + PAD + '" y="' + PAD + '" width="' +
                  (W - 2*PAD) + '" height="' + (H - 2*PAD) + '"></rect>';

    const score = labelled()
      ? ((source === "so" ? S : D).scores[(KEY0[source] || {})[key] || key] || {})["0.101"]
      : undefined;
    const shown = placed.filter(function(o){ return o.hit; }).length;

    const panel = document.createElement("div");
    panel.className = "panel " + TONE[key];
    panel.innerHTML =
      '<h4>' + LABEL[key] + '</h4>' +
      '<div class="meta">' + v.points.length + ' clusters \\u00b7 3 axes carry ' +
        Math.round(v.variance * 100) + '% of variance</div>' +
      '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' +
        v.points.length + ' clusters projected on three rotatable axes' +
        (activeGroup ? '; ' + shown + ' of them in the group ' + esc(activeGroup) : '') +
        '.">' + frame + marks + gnomon + '</svg>' +
      '<div class="stat">' +
        (activeGroup ? '<span><b>' + shown + '</b> in <b>' + esc(activeGroup) + '</b></span>'
                     : '<span><b>' + names.length + '</b> named groups</span>') +
        (score === undefined ? '' :
          '<span>recall @10.1% <b>' + score.toFixed(1) + '%</b></span>') +
      '</div>';
    host.appendChild(panel);
  });

  if (R) {
    const sr = [["text","raw episodes, embedded","a"],
                ["text-jaccard","raw episodes, free word overlap","a"],
                ["facet","facet, embedded","b"],
                ["facet-redacted","facet after mechanical redaction","b"]];
    document.getElementById("spreadrows").innerHTML = sr.map(function(r){
      const s = R.spread[r[0]] || {};
      return '<tr class="' + r[2] + '"><td>' + r[1] + '</td><td>' + (s.median ?? "-") +
             '</td><td>' + (s.p99 ?? "-") + '</td><td>' + (s.above_0_7 ?? "-") +
             '</td><td>' + (s.above_0_8 ?? "-") + '</td></tr>';
    }).join("");
  }

  const rows = [["text","raw text, embedded","a"],
                ["text-jaccard","raw text, free word overlap","a"],
                ["facet","facet, embedded","b"],
                ["facet-redacted","facet after mechanical redaction","b"]];
  // Stack Overflow names its methods title-*; the others name them text-*.
  const KEY = {"so":{"text":"title-cosine","text-jaccard":"title-jaccard",
                     "facet":"facet-cosine","facet-redacted":"facet-redacted"}};
  const SCORED = labelled() ? (source === "so" ? S : D) : D;
  document.getElementById("scorenote").textContent = labelled()
    ? "Corpus shown: " + SRC_LABEL[source] + "."
    : "WildChat carries no labels, so the table below stays on the labelled corpora.";
  document.getElementById("scores").innerHTML = rows.map(function(r){
    const k = (KEY[source] || {})[r[0]] || r[0];
    const s = SCORED.scores[k] || {};
    function cell(b){
      const v = s[b];
      return '<td>' + (v === undefined ? "-" : v.toFixed(1) + "%") + '</td>'; }
    return '<tr class="' + r[2] + '"><td>' + r[1] + '</td>' +
           cell("0.101") + cell("0.05") + cell("0.01") + '</tr>';
  }).join("");
}
render();
</script>
"""

html = (HEAD + TOP
        + SCRIPT.replace("__DATA__", json.dumps(DATA, ensure_ascii=False))
                .replace("__REAL__", json.dumps(REAL, ensure_ascii=False))
                .replace("__SO__", json.dumps(SO, ensure_ascii=False)))
out = HERE / "index.html"
out.write_text(html, encoding="utf-8")
print(f"  written: {len(html):,} bytes -> {out}")
