"""Re-validator — proof expires (invariant 6).

Contract (BLUEPRINT §5): replays the image's frozen probe set when the
served model changes (or on schedule when versions aren't exposed).
Fingerprint drift -> auto-demote to trial, log
{"op":"revalidation_failed",...}. Outputs are `Persistence`, the third
evidence type.

P3 scope — stub only in P1.
"""
