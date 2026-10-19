## Run
```bash
uv pip install fastapi "uvicorn[standard]"        # one-time (already in the venv)
uv run cle dashboard --state-dir .cle-demo --port 8000
# open http://localhost:8000
```

### Why `.cle-demo` and not `.cle`

Because of the **2. Run test** button, which runs `bash examples/full_loop.sh` -
and that script begins with `rm -rf` on the state directory it is given.

It refuses to do that to `.cle`:

```
refusing to run on .cle - set CLE_DEMO_STATE to a scratch directory
```

The refusal is deliberate. `.cle` holds the only copy of the operator's oplog,
store and topology history, it is gitignored so git cannot restore it, and a
demo is not a reason to lose it.

The button passes `CLE_STATE_DIR` through to the script as `CLE_DEMO_STATE`,
so the script writes exactly where the board is reading and the PULSE stream
moves while the run is in progress.

Launch the dashboard on `.cle` and the button is greyed out from the first
paint: the page asks `GET /health`, which answers with `demo_runnable` computed
by the same predicate the action uses, so the page cannot offer a run the
backend would refuse. Hovering gives the command to relaunch on a scratch
state, and pressing it - if anything ever bypasses the page - still refuses
before spawning. It does not simply forward the
script's own message: that one says to set `CLE_DEMO_STATE`, which is true in a
shell and unusable in a browser, because the dashboard's directory is fixed at
launch by `CLE_STATE_DIR` and nothing in the page can change it. The symptom
that replaced was a button that ran for 11 ms and stopped.

That is a change from the earlier behaviour, which is worth stating because
anyone who used the dashboard before will have seen it: the button used to
ignore the dashboard's state directory entirely and write to its own default
`.cle-demo`. It exited 0, wrote its 52 oplog lines, and the board showed
nothing - the run had succeeded somewhere nobody was watching. It looked like a
frozen dashboard and was a directory mismatch.

**The run no longer blocks.** `POST /actions/run_workspaces` starts the script
as a background task and returns in about 15 ms; the script's own step banners
reach the PULSE feed as they are printed, and a **stop run** button appears for
as long as it is in flight. `GET /health` carries `run_in_progress` so a page
loaded mid-run knows what it is looking at.

Two properties that took a second attempt to get right, and are pinned by tests:

* **One run at a time.** `full_loop.sh` begins with `rm -rf` on its state
  directory, so two concurrent runs would delete each other's work. The runner
  holds a single-flight lock and answers `409` to the second caller.
* **Stopping kills the process group, not just the shell.** `cle` and `pytest`
  run as children and inherit the stdout pipe, so killing only `bash` leaves the
  reader blocked on a pipe the grandchildren still hold - measured:
  `run_in_progress` stayed true three seconds after an abort that reported
  success. The run gets its own session and the whole group is signalled.

`GET /health`
reports which one it is (`state_dir`, `log_exists`) when the board looks empty
and you want to know why.
Populate some state first (`bash examples/full_loop.sh`, or `uv run python
examples/make_fixture.py` then `uv run cle build …`) so the board isn't empty.

**Launch it with the same backend the CLI wrote.** `$CLE_STORE` selects the
store for both, and the two hold different paths (`store/` vs `store.db`), so a
dashboard started on the other one reads an empty history and renders what looks
exactly like data loss.
