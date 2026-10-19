## Two headline findings

### 1. v1 detection only worked because the data was templated

The original fixtures repeated one identical opener per intent (the string
`"schedule the monthly gdg meetup in the main room"` appeared 45 times, once
per day, a *monthly* meetup scheduled daily). Rebuilt with genuinely varied
human phrasing (≥ 8 distinct openers per recurring intent, franglais, typos,
irregular timing), the same detector:

- **shattered every planted intent**: `events` 10 distinct openers → 9 clusters,
  `venue_policy` 8 → 8; **63 clusters for 7 planted intents**;
- **discovered nothing** on the process-independent holdout: **0 agents**
  (the templated holdout had yielded 2 of 3);
- revealed its clean metrics as artifacts: the tool-bearing `events` directive
  band went `0.0000 → 0.3381`, `ws_share_pct` `100% → 35.5%`, and the "perfect"
  `capture = 1.000` became **0.500** *even from the ideal centroid*.

Identical openers are the one input a 0.6 bag-of-tokens embedder clusters
reliably. This is a finding about the **detector**, not the data: no threshold
was tuned to soften it.

### 2. A real embedding model is not a drop-in, and it breaks contradiction detection

Swapping in `google:gemini-embedding-2:768` (frozen vectors, offline):

- at the **unchanged 0.6** threshold it fails the opposite way, **over-merging**
  everything into **2 clusters**, with `false_trigger` exploding
  **0.061 → 0.632** (events intent, ideal centroid);
- **recalibrated to 0.775** it genuinely beats v1, but GDG recovery still tops
  out at **2/7** planted intents, and of the 6 candidates it births only **2 are
  genuine** (see *Born-candidate purity*);
- it **breaks the contradiction classifier outright**: **zero divergent pairs**
  across all seven intents. Cosine measures *topical relatedness, not
  contradiction*, the planted **opposing** directives score **0.62–0.86**
  because they *are* about the same thing.

No threshold rescues the third point (the bar would have to exceed 0.86, which
flags every pair). It needs a different operator, signed / entailment, which
is its own run.

---
