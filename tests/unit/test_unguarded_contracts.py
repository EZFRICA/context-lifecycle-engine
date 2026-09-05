"""Six guards the mutation sweep found unenforced.

SCOPE — bucket 1 (embedder-agnostic): no vector space is under test.

Each `raise` here was reachable by no test, which is a different claim from
"undocumented": the code was correct and nothing would have gone red if it had
been deleted. The sweep reported 21 such sites; these are the six that carry a
contract rather than a CLI exit path, and two of them are blueprint invariants.

Every test below was run against the guard removed, and goes red.
"""

import io
import json

import pytest

from cle.build.resolver import ResolutionError
from cle.lifecycle.tags import TagMoveError, move_state_tag
from cle.oplog import OpLog
from cle.runtime.container import load_image
from cle.store.backends import InMemoryStore
from cle.store.objects import Block


def _oplog() -> tuple[OpLog, io.StringIO]:
    sink = io.StringIO()
    return OpLog(sink), sink


# ── the ladder refuses states it does not know ──────────────────────────────

def test_an_unknown_target_state_is_refused() -> None:
    """A state outside the ladder would rank as 0 and read as a demotion."""
    oplog, _ = _oplog()
    with pytest.raises(TagMoveError, match="unknown state"):
        move_state_tag(
            backend=InMemoryStore(), agent="a", image_hash="0" * 64,
            from_state="candidate", to_state="promoted",   # not on the ladder
            oplog=oplog, actor="human:test",
        )


def test_an_unknown_from_state_is_refused() -> None:
    """The dangerous half: `STATE_RANK.get(from_state, 0)` gives a typo the rank
    of `archived`, so every move out of it reads as upward and demands evidence
    that a demotion should never need. Failing loudly is the only safe reading.
    """
    oplog, _ = _oplog()
    with pytest.raises(TagMoveError, match="unknown from_state"):
        move_state_tag(
            backend=InMemoryStore(), agent="a", image_hash="0" * 64,
            from_state="candidat",                          # typo
            to_state="trial", oplog=oplog, actor="human:test",
        )


def test_an_upward_move_without_any_evidence_is_refused() -> None:
    """Invariant 4: no upward tag move without evidence. `candidate -> trial`
    rides `pre_evidence`, but it must ride something."""
    from cle.store.commits import Image, PreEvidence, TriggerSpec

    image = Image(
        source_hash="0" * 64, resolved_refs={}, assembled_prompt="p",
        trigger=TriggerSpec(centroid=(1.0, 0.0), embedder_id="stub:hashed64"),
        model_fingerprint="f" * 64,
        pre_evidence=PreEvidence(capture_rate=1.0, false_trigger_rate=0.0,
                                 historical_cost=3.0, window="30d"),
        probe_set=("p",), probe_output_hashes=("h",),
    )
    store = InMemoryStore()
    store.put(image.hash, image.canonical_bytes())
    oplog, _ = _oplog()
    with pytest.raises(TagMoveError, match="requires pre_evidence"):
        move_state_tag(
            backend=store, agent="a", image_hash=image.hash,
            from_state="candidate", to_state="trial",
            oplog=oplog, actor="human:test",
        )


# ── the oplog refuses to let context shadow the contract ────────────────────

def test_context_may_not_shadow_a_contract_key() -> None:
    """Every operation logs one JSON line whose shape is the contract.

    A caller passing `op=` or `actor=` as free context would overwrite the field
    downstream readers key on, and the line would still be valid JSON — a
    corrupted audit trail that parses. Refused at the boundary instead.
    """
    oplog, _ = _oplog()
    with pytest.raises(ValueError, match="shadow contract keys"):
        # `ts` is written into every record; `actor` cannot be reached this way
        # because it is a named parameter, so a caller cannot even try.
        oplog.emit("build", actor="human:test", ts="1999-01-01T00:00:00Z")


def test_ordinary_context_still_passes() -> None:
    """Guards the guard: a check that refused all context would pass the test
    above while making the oplog's extension point useless."""
    oplog, sink = _oplog()
    oplog.emit("build", actor="human:test", window="40d")
    assert json.loads(sink.getvalue().strip())["window"] == "40d"


# ── a hash that does not point at an image ──────────────────────────────────

def test_loading_a_non_image_by_hash_is_refused() -> None:
    """Invariant 1, two hashes: a `SourceSpec.hash` is never an `Image.hash`.

    Without this the stored record would be handed to `Image.model_validate`,
    which fails somewhere in pydantic with a message about missing fields rather
    than about the caller having addressed the wrong kind of object.
    """
    store = InMemoryStore()
    oplog, _ = _oplog()
    block = Block(kind="prompt", payload="not an image")
    store.put(block.hash, block.canonical_bytes())
    with pytest.raises(ValueError, match="is not an image"):
        load_image(store, block.hash, oplog)


# ── component refs must be refs ─────────────────────────────────────────────

def test_malformed_component_refs_are_refused() -> None:
    """`components:` holds `#ref` strings. Anything else resolves to nothing and
    would produce an image assembled from an empty component set — a build that
    succeeds and ships nothing."""
    from cle.build.resolver import resolve
    from cle.store.commits import SourceSpec

    store = InMemoryStore()
    oplog, _ = _oplog()
    spec = SourceSpec(yaml_raw=(
        "agent: a\n"
        "trigger: {}\n"
        "components: ['#ok', 42, 'no-hash']\n"
    ))
    with pytest.raises(ResolutionError, match="must be .#ref. strings"):
        resolve(spec, store, oplog, "human:test")
