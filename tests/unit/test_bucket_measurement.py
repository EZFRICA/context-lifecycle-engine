"""The rules `tools/buckets.py` classifies by, pinned on synthetic records.

SCOPE: bucket 1 (embedder-agnostic). These feed hand-written records to the pure
classification functions; no suite is run and no embedder is invoked.

The tool measures what docs/TESTING.md used to count by hand. If its rules were
wrong, the table would be precisely wrong instead of approximately wrong, so the
rules themselves are tested here.
"""

from tools.buckets import STUB, classify, declared_buckets, documented


def test_a_test_that_invoked_no_embedder_is_bucket_one() -> None:
    buckets, problems = classify({"t::a": {"embedders": [], "stub_only": False}})
    assert buckets[1] == ["t::a"] and not problems


def test_a_test_that_invoked_any_embedder_is_bucket_two() -> None:
    records = {"t::stub": {"embedders": [STUB], "stub_only": False},
               "t::gemini": {"embedders": ["google:gemini-embedding-2:768"], "stub_only": False}}
    buckets, _ = classify(records)
    assert buckets[2] == ["t::gemini", "t::stub"]


def test_a_declared_stub_only_test_that_used_the_stub_is_bucket_three() -> None:
    buckets, problems = classify({"t::a": {"embedders": [STUB], "stub_only": True}})
    assert buckets[3] == ["t::a"] and not problems


def test_a_stub_only_declaration_the_measurement_contradicts_is_reported() -> None:
    """The marker claims a dependence on the stub space; no stub call means it is false."""
    _, problems = classify({"t::a": {"embedders": [], "stub_only": True}})
    assert problems and "never embedded" in problems[0]


def test_gated_modules_are_left_out_like_the_documented_suite_size() -> None:
    records = {"tests/unit/private.py::t": {"embedders": [], "stub_only": False},
               "tests/unit/public.py::t": {"embedders": [], "stub_only": False}}
    buckets, _ = classify(records, gated=("tests/unit/private.py",))
    assert buckets[1] == ["tests/unit/public.py::t"]


def test_the_documented_counts_are_read_from_the_bucket_table() -> None:
    table = ("| **1. Embedder-agnostic** | **12** | ... |\n"
             "| **2. Stub-as-a-tool** | **3** | ... |\n"
             "| **3. Stub-as-the-subject** | **1** | ... |\n")
    assert documented(table) == {1: 12, 2: 3, 3: 1}


def test_a_scope_header_declares_its_bucket_or_nothing() -> None:
    assert declared_buckets('"""X.\n\nSCOPE: bucket 1 (embedder-agnostic). y\n"""') == {1}
    assert declared_buckets('"""X.\n\nSCOPE - `stub:hashed64` ONLY. These pin v1.\n"""') == {3}
    assert declared_buckets('"""X.\n\nSCOPE - 8 tests in bucket 1 and 2 in bucket 2.\n"""') == {1, 2}
    assert declared_buckets('"""X.\n\nNo scope here.\n"""') == set()
