#!/usr/bin/env bash
# CLE full-loop demo: detect -> build (replay) -> run x2 workspaces ->
# ps -> switch (costs) -> tag with evidence (+ engine shadow) ->
# topology diff -> revalidate with simulated model drift -> auto-demote.
# Run from the repo root:  bash examples/full_loop.sh
set -euo pipefail
CLE=.venv/bin/cle
PY=.venv/bin/python
STATE=.cle
rm -rf "$STATE"

step() { printf '\n=== %s ===\n' "$*"; }

step "1. detector writes the candidate from synthetic usage"
$PY examples/make_fixture.py

step "2. build with replay validation (adversarial window: non-trivial rates)"
$CLE build examples/weekly_recap_agent.yaml --replay-window 35d \
  --history examples/prompt_history_adversarial.jsonl

step "3. run two workspaces"
$CLE run weekly_recap --workspace alpha --prompts 2
$CLE run weekly_recap --workspace beta --prompts 4

step "4. cle ps — divergent per-container metrics"
$CLE ps

step "5. build a variant image and switch workspace alpha (diff costs)"
$PY - <<'EOF'
# Variant candidate: same trigger, one extra component.
import yaml, pathlib
src = pathlib.Path("examples/weekly_recap_agent.yaml")
doc = yaml.safe_load(src.read_text())
doc["name"] = "weekly_recap_v2"
doc["components"].append("#blocks/style_guide")
pathlib.Path("examples/weekly_recap_agent_v2.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
comp = pathlib.Path("examples/components/style_guide.yaml")
comp.write_text("ref: blocks/style_guide\nkind: prompt_fragment\npayload: |\n  House style: short sentences, active voice, no adjectives without data.\n")
EOF
$CLE build examples/weekly_recap_agent_v2.yaml --replay-window 35d \
  --history examples/prompt_history_adversarial.jsonl
$CLE run weekly_recap_v2 --workspace alpha --prompts 2
echo "--- switch line (diff_blocks / diff_tokens) ---"
grep '"op": "switch"' $STATE/log.jsonl

step "6. human promotion with lived evidence — engine shadows it"
$CLE tag weekly_recap trial
$CLE tag weekly_recap active --cost-ratio 0.6 --occurrences 4 --closures success,success,success,success

step "7. topology history and diff between versions"
$CLE log topology.yaml
echo "--- delta v1 -> v3 ---"
$CLE diff topology/v1 topology/v3

step "8. revalidation under a drifted model — proof expires"
$CLE revalidate weekly_recap --model-id drifted-model-2

step "9. last log lines (the article-9 raw material)"
$CLE log --tail 6

step "10. full test suite"
$PY -m pytest -q | tail -1
