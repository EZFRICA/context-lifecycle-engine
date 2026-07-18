"""Content hashing and stored blocks.

Contract (cle-core-contracts):
- `content_hash(obj) -> str` is THE hashing function — canonical JSON
  (sorted keys, no whitespace, UTF-8), sha256 hexdigest. Never inline
  hashlib elsewhere in the codebase.
- Every component fetched from a backend is re-hashed against the requested
  hash before use. Mismatch triggers the integrity protocol: abort use, log
  {"op":"integrity_violation",...}, refetch; never crash, never silently
  inject a corrupt component.

Implemented in commit 2 (feat(store): content hashing + integrity).
"""
