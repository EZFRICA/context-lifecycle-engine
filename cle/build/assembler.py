"""Build stage 3 — assemble.

Contract (BLUEPRINT §3.3, §9 decision 3 as adopted in the approved P1
plan): compile the system
prompt in declared order, capture `model_fingerprint` (API version if
exposed; else output hash over a fixed probe set — 12 probes drawn from the
cluster's replay window at build time, frozen into the image), hash the
complete artifact -> Image. Invariant 1: image.hash != source.hash.
Invariant 6: the fingerprint is what lets the re-validator expire proof.

Implemented in commit 9 (feat(build): assembler).
"""
