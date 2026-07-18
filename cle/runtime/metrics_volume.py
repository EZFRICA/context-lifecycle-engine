"""System-owned metrics volume — the write side of the Goodhart boundary.

Contract (cle-core-contracts, invariant 2): the runtime records
solicitations, iterations, and closure tags via
`record(container_id, event)` — one-way. Read access belongs to the
lifecycle engine and the human, never to the container.

P2 scope — interface stub only in P1.
"""
