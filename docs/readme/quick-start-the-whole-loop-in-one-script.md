## The whole loop in one script

```bash
./examples/full_loop.sh
CLE_STORE=sqlite ./examples/full_loop.sh
CLE_MODEL_A=stub-model-a CLE_MODEL_B=stub-model-b ./examples/full_loop.sh
```

Twelve steps, on **real models by default**; the third form is the offline
deterministic run CI uses. Isolate any of them with `CLE_DEMO_STATE=/tmp/scratch`
so they never touch `.cle`. All era A figures: the source is templated.

**On other live models.** `CLE_MODEL_A` and `CLE_MODEL_B` take any model name.
Add `CLE_FORCE_REAL_MODEL=1`: without it, a name the provider does not serve
falls back silently, to an offline hash for the fingerprint and to
`generation_failed` for the facet.

```bash
CLE_FORCE_REAL_MODEL=1 CLE_MODEL_A=gemini-3.6-flash CLE_MODEL_B=gemini-3.8-flash \
  CLE_DEMO_STATE=/tmp/scratch ./examples/full_loop.sh
```

Measured 2026-09-10, one run per pair, both exit 0 on every step:

| | `gemini-3.5-flash-lite` → `gemini-3.6-flash` (default) | `gemini-3.6-flash` → `gemini-3.8-flash` |
|---|---|---|
| build: capture / false trigger / cost | 1.000, 0.600 / 0.081 / 3.40, 2.67, 7.00 | identical |
| revalidation under model B | `DRIFT: 5/5 probes moved` | `DRIFT: 5/5 probes moved` |
| v2 rebuilt on model B | distinct successor image | distinct successor image |
| facets written at birth | 4 of 4 `present`, 106 to 171 characters | 4 of 4 `present`, 84 to 119 characters |

What differs between the two pairs is the facet text, and only that:

- **Length and form.** `gemini-3.5-flash-lite` writes longer sentences in the
  imperative (*"Investigate and troubleshoot sudden performance degradation
  ..."*); `gemini-3.6-flash` writes shorter ones in the third person
  (*"Investigates performance degradation ..."*). Both satisfy the prompt's
  "start with a verb", and neither was refused.
- **Separation.** Under `gemini-3.6-flash` the `weekly_recap` and
  `status_report` facets come out as near paraphrases (*weekly project status
  summaries* / *weekly project status updates and recaps*). One run cannot say
  whether that is the model or its sampling.

What does not differ, and why:

- **The build figures** are identical because replay calls no model: it
  classifies recorded episodes in the embedder's space.
- **The revalidation row** is 5/5 on both pairs, but it does not separate them.
  A live model at temperature 0 also reports drift against itself
  (`cle/llm_provider.py`, `get_fingerprint_llm`).
