#!/usr/bin/env bash
# CLE full-loop demo — exercises the whole surface on the LEGACY TEMPLATED
# demo source (make_fixture.py / prompt_history_adversarial.jsonl).
#
# IMPORTANT: numbers produced here (capture_rate, false_trigger_rate,
# historical_cost) are ERA-A figures from a TEMPLATED fixture; they do NOT
# represent realistic-usage results. See docs/METRICS.md for the full
# provenance and the realism / embedder-upgrade runs that supersede them.
#
# Three fixture sources (three distinct roles — METRICS.md §Three data sources):
#   make_fixture.py      — LEGACY TEMPLATED ground-truth + adversarial (this script)
#   make_gdg_fixture.py  — ERA-B/C realistic GDG Abidjan ground-truth (not run here)
#   make_holdout.py      — process-independent discovery; imports NOTHING from cle
#
# Optional extras (run independently after this script):
#   python examples/gdg_demo.py   — topology competition demo (capture 1.000→0.600,
#                                    planted bridge false-trigger 0.143)
#   python examples/make_vectors.py  — regenerate the committed embedding cache
#                                       (needs GEMINI_API_KEY, never run in CI)
#
# Runs on REAL models by default (real conditions): builds the fingerprint
# against a live Gemini model; v2 is born on a DIFFERENT real model to enact
# genuine drift (gemini-3.5-flash-lite → gemini-3.6-flash, 5/5 probes moved).
# Needs GEMINI_API_KEY in .env.
#
# OFFLINE / deterministic run (e.g. GitHub CI, no key) — force stub substrates:
#     CLE_MODEL_A=stub-model-a CLE_MODEL_B=stub-model-b bash examples/full_loop.sh
#
# Run from the repo root:
#     bash examples/full_loop.sh
#     uv run bash examples/full_loop.sh   # if using uv
#
# To reset state between runs without re-running the full script:
#     uv run cle clean   (or rm -rf .cle)
set -euo pipefail

CLE=.venv/bin/cle
PY=.venv/bin/python
STATE=.cle

# Adversarial window: 40-day window over the adversarial fixture (one genuine
# false-trigger "bridge" + 4 near-miss rejection traps — see METRICS.md §false_trigger_rate).
WIN=(--replay-window 40d --history examples/prompt_history_adversarial.jsonl)

# Two distinct real models — the substrate swap is what triggers genuine drift
# (5/5 probes move at revalidation, auto-demoting to trial).
MODEL_A=(--model-id "${CLE_MODEL_A:-gemini-3.5-flash-lite}")   # v1 substrate
MODEL_B=(--model-id "${CLE_MODEL_B:-gemini-3.6-flash}")         # v2 substrate — drift enacted here

# 12 successes for the pinned-promotion evidence requirement.
TWELVE=success,success,success,success,success,success,success,success,success,success,success,success

rm -rf "$STATE"
step() { printf '\n=== %s ===\n' "$*"; }

# Preflight: the suite (step 12) and several demo paths read COMMITTED fixture
# artifacts. If one is missing from the working tree the failure surfaces 11
# steps later as an opaque "error during collection", so check it up front and
# say exactly how to fix it.
missing=()
for f in examples/gdg_ground_truth.json \
         examples/prompt_history_gdg.jsonl \
         examples/prompt_history_holdout.jsonl \
         examples/vectors.google-gemini-embedding-2-768.json; do
  [ -f "$f" ] || missing+=("$f")
done
if [ ${#missing[@]} -gt 0 ]; then
  printf 'ERROR: committed fixture(s) missing from the working tree:\n'
  printf '  %s\n' "${missing[@]}"
  printf 'Restore them (they are tracked, deterministic artifacts):\n'
  printf '  git checkout -- %s\n' "${missing[@]}"
  exit 1
fi

# ---------------------------------------------------------------------------
step "1. detector writes candidates from synthetic usage (3 distinct agents)"
# ---------------------------------------------------------------------------
# make_fixture.py: 40-day TEMPLATED history — ground-truth + adversarial window.
# Outputs (regenerated on every run; the two histories are TRACKED in git, the
# agent YAMLs are not):
#   prompt_history.jsonl              — base window (ground-truth)   [tracked]
#   prompt_history_adversarial.jsonl  — adds a bridge -> false trigger [tracked]
#   <agent>_agent.yaml                — one YAML per detected candidate
#   status_report_agent.yaml          — hand-authored incumbent (not detected)
# Three clusters cross the evidence gate: weekly_recap (recurrence, 5 occ.),
# standup_digest (recurrence, 6 occ.), incident_triage (reformulation, 4 occ.).
# onboard_setup (2 occurrences) is deliberately BELOW the min=3 gate — no candidate.
# ERA-A / legacy templated source; realistic results are in make_gdg_fixture.py.
$PY examples/make_fixture.py

# ---------------------------------------------------------------------------
step "2. build agents — hand-authored status_report FIRST, then the 3 detected"
# ---------------------------------------------------------------------------
# status_report is the INCUMBENT: it owns the reworded "status report"
# phrasing exactly, so when weekly_recap is built next it competes for those
# 2 of 5 episodes → capture_rate = 0.60 (BLUEPRINT §3.2 topology competition).
echo "--- status_report (incumbent; owns the reworded 'status report' phrasing) ---"
$CLE build examples/status_report_agent.yaml "${WIN[@]}" "${MODEL_A[@]}" \
  | grep -E 'capture_rate|image_hash'

V1=""
for a in weekly_recap standup_digest incident_triage; do
  echo "--- $a ---"
  out=$($CLE build "examples/${a}_agent.yaml" "${WIN[@]}" "${MODEL_A[@]}")
  echo "$out" | grep -E 'capture_rate|false_trigger|historical_cost|image_hash'
  # Capture the weekly_recap v1 image hash for the drift comparison in step 10.
  [ "$a" = "weekly_recap" ] && V1=$(echo "$out" | grep '^image_hash' | awk '{print $2}')
done
echo "--- weekly_recap captures 60%: status_report already owns 2 of its 5 episodes ---"
echo "--- (capture_rate is measured against the CURRENT topology — BLUEPRINT §3.2) ---"
echo "--- false_trigger ~0.081 for the recap family: bridge fires, 4 traps correctly rejected ---"

# ---------------------------------------------------------------------------
step "3. run divergent workspaces (recap in alpha, incident in beta) + ps"
# ---------------------------------------------------------------------------
# One image, two workspaces → genuinely different per-container metrics.
# The Goodhart boundary: the Container has no read path to its own metrics.
$CLE run weekly_recap    --workspace alpha --prompts 2
$CLE run incident_triage --workspace beta  --prompts 5
$CLE ps

# ---------------------------------------------------------------------------
step "4. context-switch cost — swap alpha from recap to incident (different blocks)"
# ---------------------------------------------------------------------------
# diff_blocks + diff_tokens: the symmetric difference of resolved block hashes
# between outgoing and incoming images. recap→incident is a FULL disjoint swap
# (ERA-A: Δ 4 blk · 127 tok).
$CLE run incident_triage --workspace alpha --prompts 1
echo "--- switch line (real diff_blocks / diff_tokens across component sets) ---"
grep '"op": "switch"' "$STATE/log.jsonl" | tail -1

# ---------------------------------------------------------------------------
step "5. promote weekly_recap to pinned — the shadow engine judges each move"
# ---------------------------------------------------------------------------
# Every upward tag move triggers the shadow engine (actor:engine:shadow)
# which logs what it WOULD do — it never writes a ref (shadow mode only).
$CLE tag weekly_recap trial
$CLE tag weekly_recap ephemeral --cost-ratio 0.6 --occurrences 4  --closures success,success,success,success
$CLE tag weekly_recap pinned    --cost-ratio 0.5 --occurrences 12 --closures "$TWELVE"

# ---------------------------------------------------------------------------
step "6. shadow DIVERGENCE — human promotes standup on weak evidence; engine would hold"
# ---------------------------------------------------------------------------
# Promote rule: cost_ratio <= 0.7 AND occurrences >= 3.
# cost_ratio 0.95 fails the threshold → engine would: hold.
# Human overrides to ephemeral — the divergence is logged and auditable (article 9).
$CLE tag standup_digest trial
$CLE tag standup_digest ephemeral --cost-ratio 0.95 --occurrences 3 --closures success,success,reformulated
echo "--- (promote rule: cost<=0.7 & occ>=3; 0.95 fails -> would: hold, human said ephemeral) ---"
grep '"actor": "engine:shadow"' "$STATE/log.jsonl" | tail -1

# ---------------------------------------------------------------------------
step "7. demote incident_triage on cost regression — a downward move needs a reason"
# ---------------------------------------------------------------------------
$CLE tag incident_triage trial
$CLE tag incident_triage ephemeral --cost-ratio 0.7 --occurrences 3 --closures success,success,success
$CLE tag incident_triage trial --reason "cost regressed across the last three incidents"

# ---------------------------------------------------------------------------
step "7b. decline — human refuses to promote standup_digest further (article 9 audit)"
# ---------------------------------------------------------------------------
# cle decline writes NO tag and moves nothing; it records the refusal as one
# op line ("candidate_declined") so the human vs engine divergence is
# permanently auditable (article-9 data). The agent MUST exist in the topology.
# standup_digest is in ephemeral state after step 6 — a plausible proposal to
# decline further promotion.
$CLE decline standup_digest --reason "shadow engine already flagged hold; not promoting further"
grep '"op": "candidate_declined"' "$STATE/log.jsonl" | tail -1

# ---------------------------------------------------------------------------
step "8. integrity violation — tamper a stored image, then read it"
# ---------------------------------------------------------------------------
# Verify-on-read: every fetched component is re-hashed; a mismatch logs
# integrity_violation, refetches once, and raises rather than injecting corrupt bytes.
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

# ---------------------------------------------------------------------------
step "9. proof expires — revalidate pinned weekly_recap under a drifted substrate"
# ---------------------------------------------------------------------------
# Fingerprint is a CHANGE DETECTOR, not a quality detector: a better model
# demotes just as a degraded one would. Re-earning evidence under the new
# substrate is the designed cost, not a bug. (ERA-A live: 5/5 probes moved.)
$CLE revalidate weekly_recap "${MODEL_B[@]}" || true

# ---------------------------------------------------------------------------
step "10. v2 is BORN from the drift — rebuild weekly_recap on the new substrate"
# ---------------------------------------------------------------------------
# The successor is causally born from the drift: distinct image hash, distinct
# model_fingerprint. v1 (model-a) and v2 (model-b) are independent objects.
out=$($CLE build examples/weekly_recap_agent.yaml "${WIN[@]}" "${MODEL_B[@]}")
echo "$out" | grep -E 'historical_cost|image_hash'
V2=$(echo "$out" | grep '^image_hash' | awk '{print $2}')
echo "--- v1 image ${V1:0:8} (model-a) vs v2 image ${V2:0:8} (model-b) — distinct successor ---"

# ---------------------------------------------------------------------------
step "11. topology history + learned diff"
# ---------------------------------------------------------------------------
# The loop walks: 4 births, several promotions, a demotion, drift, v2 rebuild
# → the version chain runs well past a dozen entries.
# diff topology/v1 → topology/v3 renders the 3 detected agents appearing atop
# the hand-authored status_report incumbent. (See METRICS.md §Version chain.)
$CLE log topology.yaml
echo "--- delta v1 -> v3 (the three detected agents appearing atop status_report) ---"
$CLE diff topology/v1 topology/v3

# ---------------------------------------------------------------------------
step "12. full test suite"
# ---------------------------------------------------------------------------
# 219 tests across 26 files — no real model, no API key, no network needed.
# CI runs this suite plus an offline full_loop.sh smoke (CLE_MODEL_A/B=stub-*).
$PY -m pytest -q | tail -1
