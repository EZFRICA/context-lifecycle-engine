## Configuration

```bash
cp .env.example .env   # then fill in GEMINI_API_KEY
```

`cle build`, `cle run` and `cle revalidate` call the LLM configured in `.env` on
their **live path**, the local default. **No key is required to run the tests**:
the suite uses stub fingerprinters and a committed vector cache. Pin a command's substrate with
`--model-id` (`current`, a model name, or `stub-*`).

`.env` is gitignored. Fingerprint probes run at temperature 0, so a delta means
the model drifted, not that the sampler rolled differently.

**Logs.** Diagnostics (a retry, a fallback, an error a run survives) go to stderr
through `cle/logs.py`; what a command reports stays on stdout, where scripts and
tests read it, and the oplog stays the audit record. Nothing below WARNING is
shown unless `CLE_LOG_LEVEL` asks for it (`DEBUG`, `INFO`, `WARNING`, `ERROR`),
and nothing is written to disk unless `CLE_LOG_FILE` names a file - that one
rotates at 5 MiB, keeping three previous files. A log line never carries user
text: a probe is logged by its position, a failure by its exception type.

Importing `cle` configures nothing. The entry points do it - the CLI callback,
the dashboard's startup, each script's `main()` - so embedding this package in
another application leaves that application's own logging exactly as it was.

---
