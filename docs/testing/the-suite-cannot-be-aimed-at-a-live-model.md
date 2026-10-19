## The suite cannot be aimed at a live model

`CLE_EMBEDDER=real uv run pytest` looks like it works and measures nothing.
`tests/conftest.py` pops `CLE_EMBEDDER`, `CLE_STORE`, `CLE_VECTOR_CACHE`,
`CLE_STATE_DIR`, `CLE_ACTOR` and `CLE_FORCE_REAL_MODEL` in a session-scoped
autouse fixture, and neutralises `dotenv.load_dotenv` so `.env` cannot put them
back. The run that comes out is byte-identical to the plain one - same count,
same duration - and reports success for a measurement that never happened.

That is deliberate: a suite that claims to be offline by construction must not
read the operator's credentials file at all. The consequence is that **there is
no flag that makes the suite live**, and a green run says nothing about a served
model.

Point the CLI at a live substrate instead. These read the variables the suite
refuses:

```bash
uv run cle --embedder real build <src.yaml>          # live embedding space
uv run cle revalidate <agent> --model-id current     # live fingerprint probe
CLE_FORCE_REAL_MODEL=1 ./examples/full_loop.sh       # raises instead of falling back
```

The last one matters most: `CLE_FORCE_REAL_MODEL=1` makes the fingerprinter raise
on a failed probe rather than fall back to an offline hash, so a green run there
cannot be an offline run wearing a live label.
