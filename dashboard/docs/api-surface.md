## API surface
| Route | Purpose |
|---|---|
| `GET /events` | SSE; replays last 50 ops on connect, then live |
| `GET /state/ps` · `/state/candidates` · `/state/images` | snapshots |
| `GET /state/image?hash=` | one image: pre_evidence, trigger, probe count |
| `GET /state/decisions` | the op log rendered as decisions, for audit |
| `GET /state/topology?v=` · `/state/topology/versions` · `/state/topology/diff?a=&b=` | topology |
| `POST /actions/approve {agent}` · `/actions/decline {agent,reason?}` | the audience-facing write path |
| `POST /actions/init` | rebuild the demo fixture and agent |
| `POST /actions/run_workspaces` | **spends**: forces the real model (`CLE_FORCE_REAL_MODEL=1`) |
| `POST /actions/abort_run` | stops the run in progress; aborting nothing is not an error |
| `POST /actions/clean` | **destroys**: `cle clean --yes` on the state dir |
| `POST /demo/start {pace_ms}` · `/demo/abort` | demo runner |
| `GET /health` | liveness |

Every route that is not a GET is a write, and a write whose `Origin` header is
not the dashboard itself is refused with 403 before any route runs. The page is
served by the same server, so there is no CORS: another site's page can neither
read the API nor, through a bodiless POST that a browser sends without asking,
press `clean` on your behalf.

`GET /state/image` refuses any `hash` that is not 64 hex characters with a 400,
and the store refuses it a second time (`assert_object_address`): an object
address becomes a filename, so it is treated as an untrusted path component.

### Trust boundary: the machine, not the operator

**This is a decision, not an oversight.** The dashboard has no authentication,
and two of its buttons destroy state: `POST /actions/clean` runs `cle clean
--yes`, and `run_workspaces` deletes and rebuilds the state directory it is
given. What protects them is that the server binds `127.0.0.1`, that writes
carrying another site's `Origin` are refused, and that both refuse `.cle`
outright. What does NOT protect them is any check of who is asking: a local
process, or a native application able to send a request with no `Origin` header,
can press either button.

So the trust boundary is the machine. Run this as you would run a notebook
server: on a host whose local processes you trust, on a scratch state directory,
and never exposed beyond the loopback interface. A token printed at startup and
required by the destructive routes would move that boundary to the operator;
that is a change of scope for a demonstration board, and until it is made this
paragraph is the honest description of what the board defends against.

`GET /state/topology` carries an **`embedding`** field: the vector space the
history was born in (`embedder_id`, threshold, calibration). It is not optional
decoration. Centroids are only comparable inside the space that produced them,
so a reader who cannot see the space cannot interpret the states in front of
them. The payload keeps the same keys whether the store holds anything or not,
which is asserted by `tests/unit/test_dashboard_matches_disk.py`.
