"""Build stage 2 — replay validation.

Contract (replay-validation skill, BLUEPRINT §3.2, invariant 5):
Replay answers ONE question: would this candidate's trigger have fired on
the right past episodes? It can never rate answer quality — yesterday's
user cannot score an alternative answer. Outputs are `PreEvidence`
(capture_rate, false_trigger_rate, historical_cost, window) and the type
system keeps them out of promotion paths.
- false_trigger_rate MUST be computed wherever capture_rate is (replay
  out-of-cluster traffic too).
- Determinism: same window + same candidate => same report (property test).
- Replay touches no live traffic; no store writes except the build log.

Implemented in commit 8 (feat(build): replay validation).
"""
