# Context Lifecycle Engine (CLE)

> A system that lets useful agents **emerge from how you actually work**, then
> earns or revokes their standing on lived evidence, never on prediction.

Reference implementation of the *Agent OS* series (parts 7 and 8). The CLE
watches a user's prompt history, detects recurring intents that deserve their own
agent, compiles each candidate into a content-addressed **image**, validates it
by replaying the user's own past, and moves it up and down a lifecycle ladder as
evidence accumulates or expires.

It borrows vocabulary from Docker (build / image / container / volumes /
topology), Git (a Merkle store) and the APU series (block auto-detection,
promoted to whole agents), but every component justifies itself by a CLE need,
not by the analogy. `docs/BLUEPRINT.md` is the contract.

---


- [What it does, measured](docs/readme/what-it-does-measured.md) - Ten figures, each with its pinning key and reproduction command in
- [The contract, six invariants](docs/readme/the-contract-six-invariants.md) - Enforced in code, pinned by property tests.
- [Install](docs/readme/install.md) - uv venv --python 3.12
- [Configuration](docs/readme/configuration.md) - cp .env.example .env   # then fill in GEMINI_API_KEY
- [Quick start](docs/readme/quick-start.md) - uv run python examples/make_fixture.py
- [CLI reference](docs/readme/cli-reference.md) - State lives in a directory (`--state-dir`, default `.cle/`). **`--state-dir` is
- [Architecture](docs/readme/architecture.md) - openers embedded and clustered, signals counted against a **per-user baseline**; a
- [Repository layout](docs/readme/repository-layout.md) - cle/
- [Seeing the clustering](docs/readme/seeing-the-clustering.md) - uv sync --all-extras --inexact          # includes the `notebook` extra
## Testing

```bash
uv run pytest -q
```

**573 tests across 56 files**, fully offline. Five more run only where the private WildChat corpus is present, so they are not counted here: a suite size a reader cannot reproduce is not a suite size. A green suite pins the
**contract**, not the production vector space: 161 assertions are embedder
agnostic and hold in any era, while 31 pin the v1 stub mechanism only and do not
describe the production system. Details in `docs/TESTING.md`.

---


- [Status](docs/readme/status.md) - P1 to P3 of the v1 blueprint are implemented: two-hash store, three-stage build
- [Licence](docs/readme/licence.md) - is a reference implementation meant to be read and vendored, and a reader who
