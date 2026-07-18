"""Build stage 1 — resolve.

Contract (BLUEPRINT §3.1): every `#ref` in the SourceSpec exists in the
store. A missing ref fails the build in milliseconds; nothing is consumed,
nothing is written except the build log line. Resolved components are
integrity-checked (re-hashed) on fetch.

Implemented in commit 5 (feat(build): resolver).
"""
