## Demo mode
`▶ demo` (or `POST /demo/start {pace_ms}`) walks the full loop step by step at a
readable pace, flashing the zone each step affects. It uses the **live model
path**: build and the drift revalidation call the real configured LLM
(temperature 0 for the fingerprint), so "proof expires" is a genuine substrate
change. The drift step revalidates the pinned image against a *different real
model* (`CLE_DEMO_DRIFT_MODEL`, default `gemini-3.6-flash`). Single-flight;
abortable via `POST /demo/abort`.

> The demo runs `cle clean --yes` first (wipes the state dir) and makes real
> Gemini calls: it needs credentials in `.env` and consumes quota. Run it
> deliberately, not by reflex.
>
> `cle clean` asks for confirmation when a human is at a terminal, but the
> dashboard reaches it through a subprocess with no tty, so it passes `--yes`
> and the confirmation happens in the browser instead. The state dir is
> gitignored, so nothing restores it.
