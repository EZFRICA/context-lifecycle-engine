## Guards against silent failure (`cle/batch_guard.py`)

The recurring failure shape: something returns, and returning is not working.

- `assert_batch_varied` - a batch whose outputs are all identical, or whose
  error share exceeds 0.2, is a failed batch even though every call returned.
- `assert_unit_norm` - `cosine` is a raw dot product and is a cosine only on
  unit vectors. Refuses vectors from a surface that does not normalise.
- `assert_embeddable` - the only OUTBOUND guard: everything else on the
  embedding path checks what comes back, so an empty opener used to be billed
  and then clustered as if it named an intent.
