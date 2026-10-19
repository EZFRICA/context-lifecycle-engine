## Stack
- **Backend:** FastAPI. Tails `.cle/log.jsonl` and fans it out over SSE;
  serves REST snapshots; shells out to `cle` for the single write action.
- **Frontend:** one HTML page + CSS + vanilla JS with **Alpine.js** (vendored
  locally, no CDN) and native `EventSource`. No build step, no Node.
- Zero auth, zero database, the oplog *is* the database.
