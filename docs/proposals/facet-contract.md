# The agent facet, contract

**Status: PROPOSAL, for review before anything is generated.** Nothing here is
implemented.

## Why this document exists before any code

The CLE has **no naming mechanism and no description**. The
only text in `topology.yaml` is an agent name, typed by a human or hardcoded in
a fixture template. Every level-2 design so far assumes a *facet*, a
descriptive text, written by the engine, that a population level embeds and
groups.

That component does not exist, and it would be **the first in this project to
produce prose by model**. Two properties of the codebase make writing the
contract first non-optional:

- `FreeTextInTopologyError` exists precisely to keep prose out of
  `topology.yaml`. A facet is prose. Adding it without a contract would reopen,
  by hand, the boundary the closed vocabulary shuts structurally.
- An open question: Clio embeds summaries of
  **conversations**; a facet is a summary of an **agent**, which is a more
  abstract object. Nothing establishes that they group as well.

---

## a. What the facet contains

| property | value | why this value |
|---|---|---|
| length | **40–300 characters**, hard bounds | Long enough to distinguish two agents in one domain; short enough that an embedding is dominated by the task, not by prose style. Both bounds are validated, not advisory. |
| language | **English**, always, **now measured, no longer a hypothesis** |
| form | one sentence, verb-first, describing **what the agent does** | Not what the user is, not what the domain is. "Drafts weekly project recaps for a team", not "Project management". |
| forbidden | proper nouns, personal names, organisation names, URLs, file paths, numbers longer than 2 digits, any verbatim span of ≥ 6 words from the source | Each is a leak channel, and each is mechanically checkable, see §d. |

## b. Where it is produced from, and the leak this creates

The facet is generated **from the episodes of the cluster**, which are **raw
user text**. This is Clio's layer 1, and it is the only place in the CLE where
user text passes through a model to produce something that will be stored.

The prompt must therefore, explicitly and in its own words:

1. instruct that no private information be reproduced;
2. forbid proper nouns of every kind, people, companies, products, places;
3. forbid quoting; the output describes a *kind of task*, not an instance;
4. state that the summary will be read by someone who has no access to the
   source, so anything that only makes sense with the source is wrong.

**This is the weakest link in the design, and it should be named as such.** A
prompt instruction is not a guard. §d exists because the
instruction alone cannot be trusted; the measurement of what leaks anyway is
part of the deliverable, not a follow-up.

## c. When it is produced, once, and determinism is NOT required

**At the birth of the agent, once, and never regenerated.**

A served model is not deterministic at temperature 0 (measured, 3/3
runs produced distinct fingerprints on an identical probe set. That finding
does **not** apply here, and the distinction is worth stating because it is easy
to import the wrong lesson:

- **Drift detection compares a value to a later regeneration of itself.** It
  requires determinism, which is unavailable here, and is why the live
  revalidation path is blocked from writing topology.
- **Aggregation compares a value to *other agents' values*.** It requires that
  the space be consistent, not that the generator be reproducible. A facet
  generated once and stored is a fixed point; nothing ever regenerates it to
  compare.

So non-determinism costs nothing here. What it does mean is that **a facet is
not reproducible from the corpus**: it is data, not a derivation, and it must be
preserved like data. Losing it means losing it.

## d. Where it lives, and under what type

**Proposal: a distinct type, `Facet`, engine-written only, with its own guard.
The difference from free text must be mechanical, not documentary.**

Four mechanisms, each of which fails loudly:

1. **A frozen model with validators**, not a `str`. Length bounds, a rejection of
   URLs, of digit runs longer than 2, and of a capitalised-token heuristic for
   proper nouns. A `Facet` that violates any of these cannot be constructed.

2. **Verbatim-overlap validation at construction.** The builder takes the source
   episodes and refuses any facet sharing a span of ≥ 6 words with them. This is
   the check the prompt instruction cannot make. It lives in the builder rather
   than the type, because only the builder has the source.

3. **One construction site, asserted by an AST scrape.** `Facet(` may appear in
   exactly one module, the generator, exactly as
   `tests/property/test_closed_vocabulary.py` asserts for the reason vocabulary.
   A human path to constructing one would make every other guard decorative.

4. **No CLI surface.** There is no flag by which a human supplies a facet. The
   CLI is the one write surface, so a field with no flag has no human
   path.

**`FreeTextInTopologyError` is NOT relaxed.** It refuses prose under
`cause["reason"]`, and it continues to. A facet travels as its own typed
parameter, the way `reason: TopologyReason | None` and
`embedding: EmbeddingConfig | None` already do, the pattern exists and this
follows it rather than inventing a second one.

**The honest caveat on mechanism 1.** A capitalised-token heuristic has false
positives (sentence starts, "I", acronyms that are legitimately generic) and
false negatives (lowercase product names, names in scripts without case). It
narrows the channel; it does not close it. Anyone reading a facet aggregate must
know that.

## d-bis. Two consequences of §c and §d, from the review

**The facet is DATA, not a derivation.** It cannot be recomputed from the
corpus, §c makes it a fixed point generated once, so it lives in the
append-only chain like everything else, and losing it means losing it. This is
the opposite of a centroid, which any run can rebuild from the same episodes.
Anything that treats facets as regenerable is wrong about them.

**Agents born before facets exist will never have one.** There is no
back-generation: their episodes are still in the store, but a facet generated
today from a cluster judged years ago would carry today's model and today's
prompt while claiming to describe that birth. That is the false-`Persistence`
shape, an artefact presented as a record of something it did not
witness.

So: **KNOWN DIVERGENCE, with a cut-off date**, recorded the same way as for the
topology records that keep a false cause. A population aggregate must be able to
tell "no facet because the agent predates facets" from "no facet because
generation failed", and that distinction has to be representable, not inferred
from a null.

## e. What the facet is not

- **Not a replacement for the agent name.** The naming gap stays
  open. A facet describes; a name identifies. Conflating them would make the
  facet load-bearing for identity, and identity is content-addressed here.
- **Not a carrier of a centroid, a probe, or quoted user text.** Those live in
  the store image, which level 2 does not read (invariant 4).
- **Not evidence.** It plays no part in the ladder. It gates no promotion and
  justifies no demotion; `PreEvidence` / `Evidence` / `Persistence` remain the
  three and only standards of proof.
- **Not regenerated on drift.** See §c.

---

## What this contract does not settle

- **Whether facets group at all.** Open, and the lexical baseline
  is the bar: on Stack Overflow, Jaccard separated at 62.2% / 10.1% and the
  embedding gained only 11.7 points. A facet mechanism that does not beat a free
  lexical method would mean level 2 needs no embeddings at all.
- **Which vector space.** Still open, and three exist.
- **The minimum population threshold.** Tied to scale: at 0.34% of users
  producing a topology, 340 topologies presume ~100,000 users.
