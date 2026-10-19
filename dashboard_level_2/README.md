# Level 2 cluster board

A single self-contained `index.html`. No server, no build step, no dependency at
view time: the data is embedded, so the file opens from disk.

```bash
open dashboard_level_2/index.html
```

Or serve the repo if your browser blocks local fonts:

```bash
uv run python -m http.server 8090   # then http://localhost:8090/dashboard_level_2/
```


- [What it is for](docs/what-it-is-for.md) - The CLE's question is not how to create agents - there is no shortage of those -
- [Three corpora, three questions](docs/three-corpora-three-questions.md) - A selector switches between them. They are not interchangeable and the page says
- [Discovered intents, and why they are not labels](docs/discovered-intents-and-why-they-are-not-labels.md) - Only GDG carries intents; a generator planted them. `discover_intents.py` supplies
- [How the stages map to Clio](docs/how-the-stages-map-to-clio.md) - of unique users or conversations". A group is named only with at least 3 members
- [The plot](docs/the-plot.md) - Hand-drawn SVG: three PCA axes rotated orthographically by two sliders. The
- [Rebuilding it](docs/rebuilding-it.md) - The exports and the discovery bill BigQuery; the build does not.
- [What the published board contains, about real people](docs/what-the-published-board-contains-about-real-p.md) - is derived from real WildChat conversations: 130 facets from 40 users, each point
- [What the numbers are, and are not](docs/what-the-numbers-are-and-are-not.md) - corpus into 12 synthetic users and every message carries its intent in
