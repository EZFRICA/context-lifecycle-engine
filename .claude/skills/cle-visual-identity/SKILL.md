---
name: cle-visual-identity
description: Colors, typography, and component styling for the CLE dashboard, matching the Agent OS series visual identity. Use when writing any CSS, Tailwind config, or component markup.
---

# CLE Visual Identity

The dashboard must look like the series artwork come alive — the audience
has seen the article covers; the live system should be recognizably the
same object.

## Palette (dark theme only)
- Background: gradient #0d1117 → #131a22; panels #171d23 with 1px #2a333c
  borders, 10–14px radius; subtle grid lines #1c2530 acceptable on the
  main canvas.
- Ink: #dce3e8 primary, #8a97a3 muted, #6b7784 faint.
- Semantic accents (fixed, non-negotiable):
  - blue  #5aa9e6 → sources, candidates, pre_evidence
  - teal  #3dbf9b → built images, evidence, promotions, success
  - amber #e8a33d → pinned, human gate (Force Override), warnings
  - coral #e8705a → demotions, failures, integrity alerts
  - violet #9b8cf2 → topology, trial state
- Lifecycle states. FIVE exist in the code and only these may be rendered
  as chips: archived #6b7784 (dashed border) · candidate #5aa9e6 ·
  trial #9b8cf2 · ephemeral #3dbf9b · pinned #e8a33d (filled chip, dark
  text — the only filled state, it "earned its place").
  The published part-7 machine also names `pattern` (#8a97a3) and
  `deprecated` (#e8705a); their colors are reserved but the store cannot
  hold those states, so the UI must not show them as if it could.

## Typography
- Mono for all data (JetBrains Mono, fallback ui-monospace): hashes,
  metrics, log lines, YAML. Hashes always 8 chars + ellipsis.
- Sans (system stack) only for headings and prose captions.
- Eyebrow style for zone titles: 12px mono, letter-spacing 0.14em,
  uppercase, muted.

## Components
- PULSE lines: single-line mono, op name colored by its semantic accent,
  ts right-aligned faint; integrity_violation gets a full-width coral
  band, not a line.
- Cards (candidates, images): panel style, colored 1.5px border matching
  state, window-chrome dots (coral/amber/teal 5px) on file-like cards
  (YAML, topology) as in the series covers.
- Evidence badges: small rounded chips, mono 12px, colored per evidence
  type; switch cost badges: `Δ 1 blk · 10 tok` format.
- Disclosed gaps are NOT badges. An absent measurement (e.g. the
  contradiction check that could not run) renders as a dashed amber rule +
  dashed marker + muted note — deliberately unlike the solid evidence
  chips, so a missing value can never be misread as a measured one.
- Buttons: outline style in the accent color; the Approve button is amber
  (it IS the Force Override); destructive/decline is coral outline.
- Motion: subtle only — PULSE lines slide in 150ms; zone flash in demo
  mode = 1px border glow 600ms; the revalidation failure may pulse coral
  twice. Nothing else animates. prefers-reduced-motion disables all.

## Copy tone
Short, mono-adjacent, honest. Captions state limits inline
("trigger only — not answer quality", "synthetic closures"). No marketing
adjectives anywhere in the UI.
