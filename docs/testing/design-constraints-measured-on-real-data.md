## Design constraints measured on real data

Figures measured on real corpora live in `docs/FINDINGS.md`, each with its
pinning key and its reproduction command. Four constraints came out of that work
and must survive any redesign:

1. **The signal is a tail effect, never a mean.** An aggregator reading mean
   similarity sees ~0.55 everywhere and concludes nothing.
2. **No dedicated vector storage is justified at this scale.** Exhaustive search
   stays under 3 s at one million vectors.
3. **Reformulation false positive rates are UPPER BOUNDS.** A control pair is one
   no moderator closed, which is the absence of a judgment, not a judgment of
   distinctness.
4. **Three vector spaces exist**, and `bigquery:gemini-embedding-001:768` is a
   different model from the CLE's, not a different surface onto the same one.
   Cosine between them on the same texts: 0.040084. (BigQuery can host
   `gemini-embedding-2` since 2026-10-05, which makes a fourth space possible;
   no figure here has been measured in it.)
