## d. Where it lives, and under what type

**A distinct type, `Facet`, engine-written only, with its own guard. The
difference from free text is mechanical, not documentary.**

Four mechanisms, each of which fails loudly:

1. **A frozen model with validators**, not a `str`. Length bounds, a rejection of
   URLs, of digit runs longer than 2, and of a capitalised-token heuristic for
   proper nouns. A `Facet` that violates any of these cannot be constructed.

2. **Verbatim-overlap validation at construction.** The builder takes the source
   episodes and refuses any facet sharing a span of ≥ 6 words with them. This is
   the check the prompt instruction cannot make. It lives in the builder rather
   than the type, because only the builder has the source.

3. **One construction module, asserted by an AST scrape.** A `Facet` is built
   only in `cle/population/facet.py`: `build_facet` for a new one,
   `facet_from_record` when reading one back from a topology, which re-validates
   it. `tests/unit/test_population_facet.py` asserts it, as
   `tests/property/test_closed_vocabulary.py` does for the reason vocabulary.
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
