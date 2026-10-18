## 3. What the detector's floor actually is


The floor is not about how much a user writes.

| threshold | what it buys |
|---|---|
| ~6 occurrences of one intent | a first cluster forms |
| ~10 occurrences of one intent | recovery is reliable |

**Episode count predicts nothing.** A user with 200 episodes spread across 200
distinct intents produces no cluster; a user with 30 episodes across 3 intents
produces 3. The quantity that matters is occurrences per intent, which is
recurrence behaving as recurrence.

Pinning key: `(2026-08-30, eca74ca+wt, google:gemini-embedding-2:768 @ 0.775,
stub-model-1)`.

```bash
uv run python examples/make_multiuser.py && uv run python examples/density_probe.py
uv run python examples/criterion_probe.py
```

---
