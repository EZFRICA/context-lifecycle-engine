## CLI reference

State lives in a directory (`--state-dir`, default `.cle/`). **`--state-dir` is
per command and goes AFTER the subcommand; `$CLE_STATE_DIR` is read by the
dashboard, never by the CLI.** `--store {file,sqlite}` is global and goes
**before** it:

```bash
uv run cle --store sqlite build ...      # not: cle build --store sqlite
```

The backends hold different paths (`.cle/store/` vs `.cle/store.db`), so
switching starts an empty store rather than half reading the other. The dashboard
sees what the CLI wrote only if launched with the same setting.

| Command | What it does |
|---|---|
| `cle build <src.yaml>` | Resolve, replay-validate, assemble; births the candidate. Replays against the current topology, so incumbents compete. `--replay-window`, `--history`, `--components`, `--model-id`. |
| `cle run <agent> --workspace <ws>` | Instantiate or switch the workspace's container and solicit it. `--prompts N`. |
| `cle ps` | Containers and their per-container metrics. |
| `cle tag <agent> <state>` | Move a state tag (`--cost-ratio`, `--occurrences`, `--closures`, `--reason`, `--note`). |
| `cle log [topology.yaml]` | Op-log tail, or topology history with provenance. |
| `cle diff <vA> <vB>` | Learned-topology delta between two versions. |
| `cle revalidate <agent>` | Replay the frozen probe set; on drift, auto-demote to `trial`. |
| `cle decline <agent>` | Refuse what the system proposes for an agent (a birth, or a further promotion). Logs the refusal, moves no tag; `--reason` takes only `engine_disagrees` or `defer`. |
| `cle population <dir>...` | Level 2: group the agents of many instances by their facets. Reads each `topology.yaml` only, writes `report.json` under `--out`. `--threshold`, `--namer stub\|live`. |
| `cle dashboard` | Launch the FastAPI dashboard. `--port`. |
| `cle clean` | Reset the state directory. **Confirms first**; `--yes` to skip. |

`--model-id` defaults to `current`: the **live, billed** model.

---
