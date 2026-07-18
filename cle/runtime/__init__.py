"""Runtime — containers, mounts, metrics volume (P2 scope).

CLE need: one image serves many workspaces; per-container metrics feed the
lifecycle engine without ever feeding the agent itself (invariant 2, the
Goodhart boundary). P1 ships only the Container record stub so the boundary
is enforced by test from day one.
"""
