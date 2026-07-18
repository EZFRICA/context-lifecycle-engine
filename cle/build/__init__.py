"""Three-stage build: resolve -> replay-validate -> assemble.

CLE need: agents born from usage have no a-priori eval suite; their own
history is the suite (BLUEPRINT §3, APU lineage). Invariant 3: a failed
stage burns zero trial occurrences and writes nothing except the build log.
"""
