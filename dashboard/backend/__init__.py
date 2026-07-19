"""CLE live dashboard — read-mostly window onto a running CLE.

Feeds exclusively on CLE artifacts under the state dir (default .cle/):
the oplog (log.jsonl) and the FileStore (images, tags, topology). It reads
by importing CLE's own read helpers; it writes ONLY by shelling out to the
`cle` CLI (Approve/Decline), so the store is never touched directly. This
keeps the Goodhart boundary intact: metrics are the human's window here,
never fed back to an agent.
"""
