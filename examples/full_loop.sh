#!/usr/bin/env bash
# CLE full-loop demo — exercises the whole surface on the synthetic fixtures.
# Runs on REAL models by default (real conditions): builds fingerprint against
# a live Gemini model, v2 is born on a DIFFERENT real model to enact genuine
# drift. Needs a GEMINI_API_KEY in .env. For an OFFLINE / deterministic run
# (e.g. GitHub CI, no key), force stub substrates:
#     CLE_MODEL_A=stub-model-a CLE_MODEL_B=stub-model-b bash examples/full_loop.sh
# Run from the repo root:  bash examples/full_loop.sh
set -euo pipefail
CLE=.venv/bin/cle
PY=.venv/bin/python
STATE=.cle
WIN=(--replay-window 40d --history examples/prompt_history_adversarial.jsonl)
MODEL_A=(--model-id "${CLE_MODEL_A:-gemini-3.5-flash-lite}")  # substrate v1 is proven on
MODEL_B=(--model-id "${CLE_MODEL_B:-gemini-3.6-flash}")    # a DIFFERENT real model — v2 is born here
TWELVE=success,success,success,success,success,success,success,success,success,success,success,success
rm -rf "$STATE"
step() { printf '\n=== %s ===\n' "$*"; }

step "1. detector writes candidates from synthetic usage (3 distinct agents)"
$PY examples/make_fixture.py

step "2. build agents — hand-authored status_report FIRST, then the 3 detected"
echo "--- status_report (incumbent; owns the reworded 'status report' phrasing) ---"
$CLE build examples/status_report_agent.yaml "${WIN[@]}" "${MODEL_A[@]}" \
  | grep -E 'capture_rate|image_hash'
V1=""
for a in weekly_recap standup_digest incident_triage; do
  echo "--- $a ---"
  out=$($CLE build "examples/${a}_agent.yaml" "${WIN[@]}" "${MODEL_A[@]}")
  echo "$out" | grep -E 'capture_rate|false_trigger|historical_cost|image_hash'
  [ "$a" = "weekly_recap" ] && V1=$(echo "$out" | grep '^image_hash' | awk '{print $2}')
done
echo "--- weekly_recap captures 60%: status_report already owns 2 of its 5 episodes ---"
echo "--- (capture_rate is measured against the CURRENT topology — BLUEPRINT §3.2) ---"

step "3. run divergent workspaces (recap in alpha, incident in beta) + ps"
$CLE run weekly_recap    --workspace alpha --prompts 2
$CLE run incident_triage --workspace beta  --prompts 5
$CLE ps

step "4. context-switch cost — swap alpha from recap to incident (different blocks)"
$CLE run incident_triage --workspace alpha --prompts 1
echo "--- switch line (real diff_blocks / diff_tokens across component sets) ---"
grep '"op": "switch"' "$STATE/log.jsonl" | tail -1

step "5. promote weekly_recap to pinned — the shadow engine judges each move"
$CLE tag weekly_recap trial
$CLE tag weekly_recap ephemeral --cost-ratio 0.6 --occurrences 4  --closures success,success,success,success
$CLE tag weekly_recap pinned    --cost-ratio 0.5 --occurrences 12 --closures "$TWELVE"

step "6. shadow DIVERGENCE — human promotes standup on weak evidence; engine would hold"
$CLE tag standup_digest trial
$CLE tag standup_digest ephemeral --cost-ratio 0.95 --occurrences 3 --closures success,success,reformulated
echo "--- (promote rule is cost<=0.7 & occ>=3; 0.95 fails -> would: hold, human said ephemeral) ---"
grep '"actor": "engine:shadow"' "$STATE/log.jsonl" | tail -1

step "7. demote incident_triage on cost regression — a downward move needs a reason"
$CLE tag incident_triage trial
$CLE tag incident_triage ephemeral --cost-ratio 0.7 --occurrences 3 --closures success,success,success
$CLE tag incident_triage trial --reason "cost regressed across the last three incidents"

step "8. integrity violation — tamper a stored image, then read it"
$PY - <<'EOF'
import pathlib
from cle.store.backends import FileStore
from cle.lifecycle.topology import current_agents
s = FileStore(".cle/store"); h = current_agents(s)["incident_triage"]["image"]
p = pathlib.Path(".cle/store/objects") / h
p.write_bytes(p.read_bytes() + b"tampered")
print("corrupted incident_triage image", h[:8])
EOF
$CLE run incident_triage --workspace gamma --prompts 1 >/dev/null 2>&1 || true
echo "--- integrity_violation fired on the corrupt read ---"
grep '"op": "integrity_violation"' "$STATE/log.jsonl" | tail -1 || echo "(none)"

step "9. proof expires — revalidate pinned weekly_recap under a drifted substrate"
$CLE revalidate weekly_recap "${MODEL_B[@]}" || true

step "10. v2 is BORN from the drift — rebuild weekly_recap on the new substrate"
out=$($CLE build examples/weekly_recap_agent.yaml "${WIN[@]}" "${MODEL_B[@]}")
echo "$out" | grep -E 'historical_cost|image_hash'
V2=$(echo "$out" | grep '^image_hash' | awk '{print $2}')
echo "--- v1 image ${V1:0:8} (model-a) vs v2 image ${V2:0:8} (model-b) — distinct successor ---"

step "11. topology history + learned diff"
$CLE log topology.yaml
echo "--- delta v1 -> v4 (the three detected agents appearing atop status_report) ---"
$CLE diff topology/v1 topology/v4

step "12. full test suite"
$PY -m pytest -q | tail -1
