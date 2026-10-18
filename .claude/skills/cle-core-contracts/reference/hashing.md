## Hashing
- One function: `content_hash(obj) -> str` - canonical JSON (sorted keys, no
  whitespace, UTF-8), sha256 hexdigest. Never inline hashlib elsewhere.
- Verify on read: every component fetched is re-hashed against the requested
  hash before use. Mismatch → integrity protocol: abort use, log
  `{"op":"integrity_violation",...}`, refetch from backend; never crash,
  never silently inject.
