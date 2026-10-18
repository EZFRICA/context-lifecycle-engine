## Tests that must exist before the code they guard
1. `test_two_hash_inequality` - build never yields image.hash == source.hash.
2. `test_tag_source_raises` - TagTargetError on tagging a source hash.
3. `test_goodhart_boundary` - reflection: no attribute/method on Container
   returns metrics.
4. `test_staged_failure_writes_nothing` - failed resolve/replay leaves store
   byte-identical (snapshot compare).
5. `test_pre_evidence_not_evidence` - type-level: promotion API rejects
   PreEvidence.
6. `test_build_determinism` - hypothesis: same inputs ⇒ same image hash.
7. `test_embedder_swap_changes_the_image_hash` (+ cross-space comparison
   raises) - centroid provenance is part of agent identity.
8. `test_vector_cache_has_one_distinct_vector_per_text` - a silent batching
   collapse in the committed cache must fail the suite, not be eyeballed.
9. One test per RAISE SITE of every guard, not one per exception class. R36
   mutated each `raise` in turn and found three unenforced: `cosine`'s
   dimension check had no test at all, and two of the three
   `SpaceMismatchError` sites were free because the third looked covered. An
   exception class appearing in a test file proves nothing about the site you
   care about.
10. `$CLE_VECTOR_CACHE` is a PATH override, never a SPACE override. A cache
   declaring a foreign `embedder_id` must still be refused at the topology
   write, including when someone adds its calibration entry.
