## Architecture

**Two pillars.** *Detection*: episodes segmented on silence and explicit markers,
openers embedded and clustered, signals counted against a **per-user baseline**; a
cold user (<14 days, <20 episodes) gets no candidates. *Lifecycle*: candidates are
built, trialed, promoted, demoted, archived, resurrected, re-validated.

**Three-stage build.** *Resolve*: every `#ref` exists and re-hashes to its
address, or the build fails in milliseconds having written nothing.
*Replay-validate*: re-segment the window, route it against the topology plus the
candidate, report `capture_rate`, `false_trigger_rate` and `historical_cost` as
`PreEvidence`. *Assemble*: compile in declared order, freeze the probe set and
`model_fingerprint`, hash into an `Image`.

**The embedder is a substrate.** Three implementations behind one Protocol:
`RealEmbedder` (live, the only one needing a key), `CachedEmbedder` over committed
vectors (the suite default, a miss is an error), `StubEmbedder`. `TriggerSpec`
records `embedder_id` and `Image.hash` covers the trigger, so two images built on
different embedders have different hashes, and cross-space comparison raises. The
threshold travels with `embedder_id`: 0.6 for the stub, 0.775 for the real
embedder. One number cannot serve both.

**Ladder, five states in v1.** `archived(0) <-> candidate(1) <-> trial(2) <->
ephemeral(3) <-> pinned(4)`. `ephemeral` is promoted on lived `Evidence`;
`pinned` needs stability over ≥10 solicitations at non-worsening cost. The
**shadow engine** runs the part 7 thresholds and logs what it would do without
ever writing a ref.

> **Known divergence.** The published theory names **seven** states; v1
> implements **five**. Not reconciled, recorded rather than papered over.

**Three standards of proof.** `PreEvidence` (replay), `Evidence` (lived) and
`Persistence` (drift) are distinct types, so a function wanting `Evidence`
rejects the other two at type level. **Store**: content-addressed behind a
Protocol (`InMemoryStore`, `FileStore` default, `SqliteStore`), selected through
one `open_store` factory, all local. `topology.yaml` is written only by
`lifecycle/topology.py`, and a property test enforces that.

---
