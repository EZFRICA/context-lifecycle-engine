## Quick start

```bash
# 1. Generate the LEGACY TEMPLATED demo history. The DETECTOR writes one agent
#    yaml per pattern, plus a hand-authored status_report incumbent.
uv run python examples/make_fixture.py

# 2. Three-stage build. capture_rate is measured against the CURRENT topology,
#    so build status_report first and weekly_recap drops to 0.60: the incumbent
#    already owns two of its episodes.
uv run cle build examples/weekly_recap_agent.yaml \
  --replay-window 40d --history examples/prompt_history_adversarial.jsonl

# 3. Instantiate in two workspaces and solicit.
uv run cle run weekly_recap --workspace alpha --prompts 2
uv run cle run weekly_recap --workspace beta  --prompts 4

# 4. Divergent per-container metrics, read across the Goodhart boundary.
uv run cle ps

# 5. Promote on lived evidence; the shadow engine judges the same evidence.
uv run cle tag weekly_recap trial
uv run cle tag weekly_recap ephemeral \
  --cost-ratio 0.6 --occurrences 4 --closures success,success,success,success

# 6. Topology history and the learned-topology delta.
uv run cle log topology.yaml
uv run cle diff topology/v1 topology/v3

# 7. Revalidate under a drifted model: proof expires, the agent auto-demotes.
uv run cle revalidate weekly_recap --model-id drifted-model-2
```


- [The whole loop in one script](quick-start-the-whole-loop-in-one-script.md)
- [Live dashboard](quick-start-live-dashboard.md)
- [Level 2: the population layer](quick-start-level-2-the-population-layer.md)
- [Level 2 board](quick-start-level-2-board.md)
