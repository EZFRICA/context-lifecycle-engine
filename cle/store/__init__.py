"""Two-hash Merkle store (Git lineage).

CLE need: candidates and images must be content-addressed so that lifecycle
tags point at exact, tamper-evident artifacts (BLUEPRINT §1, invariant 1).
Source hashes and image hashes are distinct namespaces; tags attach to image
hashes only.
"""
