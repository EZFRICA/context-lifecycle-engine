## What this contract does not settle

- **Whether a deployment should store facets at all.** Measured, not decided:
  on real users with real labels raw text groups better (61.1% against 54.8% for
  the redacted facet at a 10.1% budget, `docs/FINDINGS.md` §6b-ter), and the
  ranking of methods depends on the error budget (§6c). Whether the population
  layer may hold user text is the deployer's constraint, not a score.
- **Which vector space.** `cle population` embeds in the instance's configured
  space; every bench figure above was measured in BigQuery's. No facet threshold
  is calibrated in the engine's space.
- **The right population floor.** The one that exists is a single global floor
  of 3 distinct users (`cle/population/privacy.py`), and it is known to be
  insufficient (BLUEPRINT §7c). It is also tied to scale: at 0.34% of users
  producing a topology, 340 topologies presume about 100,000 users.
- **Whether `FACET_PROMPT` should fence its sources.** User text enters that
  prompt directly, so a request can carry a sentence addressed to the model, and
  the mechanical screens of §a catch the shapes an IDENTIFIER takes - a URL, a
  path, a long number, a capitalised token, a six-word verbatim span - not a
  plain instruction. The NAMING prompt downstream was fenced
  (`cle/population/naming.py`), and what that cost is worth knowing before anyone
  fences this one: the first attempt made a live model MIMIC the markers and
  answer `<<<\nName: x\n>>>`, which the identifier screen then refused, so a
  correct name was lost until an explicit output-format line was added - and the
  prompt became `name-prompt-v2`, which makes every name produced under v1 a
  figure about a prompt that no longer exists. This one is deliberately left as
  it is, for the same kind of reason at a larger scale - provenance, not risk:
  the prompt's text is part of
  `generator_id` through `FACET_PROMPT_VERSION`, every committed facet and every
  measurement in `docs/FINDINGS.md` was produced under `facet-prompt-v1`, and a
  new version would make each of those figures a figure about a prompt that no
  longer exists. §c already forbids regenerating a facet, so the old ones could
  not be brought forward either. The bound on the damage is unchanged and is
  stated in §a: whatever the model writes, `build_facet` refuses what the
  contract does not allow, and a facet gates nothing (§e). Changing this is a
  version bump and a re-measurement, not an edit.
