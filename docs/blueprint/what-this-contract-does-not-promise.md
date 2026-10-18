## 10. What this contract does not promise

Stated here so no reader infers it from the sections above:

- Replay proves a **trigger**, never answer quality, and never the temporal
  period (`period_tested` is always false in v1).
- A fingerprint delta proves the **substrate changed**, not that the agent got
  worse; a better model demotes exactly as a degraded one does.
- Detection **recovering** a user's real intents is a measured quantity, not a
  contractual guarantee. On realistic data v1 recovers a minority of planted
  intents (`docs/METRICS.md`); the mechanisms above are what the system *does*,
  not a claim about how well.
- The lifecycle engine is in **shadow mode**: humans move every tag.
- The oplog is **append-only, not tamper-evident**. Invariant 4 governs what the
  engine writes - one line per operation, never a rewrite - and the store
  verifies every object it reads against its hash. The log file itself has no
  such protection: no HMAC, no signature, no line carrying the hash of the
  previous one, so anyone who can write the file can edit history and nothing
  detects it. A hash chain would close this, and it is a change of design rather
  than a patch: every reader (`cle log`, `cle diff`, the dashboard tailer, the
  oplog view tests) would have to verify the chain, and a broken chain would
  need a defined behaviour. Recorded here, not scheduled.
- The dashboard's trust boundary is **the machine it runs on**, not the user at
  the keyboard. It binds `127.0.0.1`, refuses writes carrying another site's
  `Origin`, and refuses `.cle` for the two destructive buttons - but it has no
  authentication, so any local process, or any native application able to send
  a request without an `Origin` header, can reach `POST /actions/clean`. Run it
  on a machine whose local processes you trust, as you would a notebook server.
  See `dashboard/README.md`.
