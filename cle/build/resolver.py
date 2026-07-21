"""Build stage 1 — resolve.

Contract (BLUEPRINT §3, stage 1): every `#ref` in the SourceSpec exists in
the store. A missing ref fails the build in milliseconds; nothing is
consumed, nothing is written except the build log line (invariant 3).
Resolved components are integrity-checked (re-hashed) on fetch.

Ref forms (blueprint names the syntax `#ref` and is silent on shapes; two
forms cover both authorship paths):
- `#<64-hex>` — direct content address, as the detector writes it.
- `#<ref-name>` — a name in the store's ref table, as a human writes it.
Both resolve to a content hash whose object must exist and verify.
"""

import json
import re
import time

import yaml

from cle.oplog import OpLog
from cle.store.backends import StoreBackend
from cle.store.commits import SourceSpec
from cle.store.objects import IntegrityError, fetch_verified

# Precedence: a ref matching this is ALWAYS a direct content address; a
# ref-table name of exactly 64 hex chars is unreachable (real names carry
# slashes: agents/…, blocks/…).
_HASH_REF = re.compile(r"^#[0-9a-f]{64}$")


class ResolutionError(Exception):
    """Stage-1 failure; carries every missing ref so one build attempt
    reports the whole gap, not just the first hole."""

    def __init__(self, message: str, missing_refs: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.missing_refs = missing_refs


def resolve(
    source: SourceSpec, backend: StoreBackend, oplog: OpLog, actor: str
) -> dict[str, str]:
    """Resolve every component ref of a candidate source to a content hash.

    Returns the resolved_refs mapping the Image will freeze (ref as
    written -> content hash). Raises ResolutionError (structural problem
    or the full sorted list of missing refs) or IntegrityError (a
    component exists but fails verification); on any failure path the only
    write is the build log line naming this stage. `actor` comes from the
    initiator (the CLI passes human:<id>) — a stage never invents one.
    """
    started = time.monotonic()
    try:
        return _resolve_refs(source, backend, oplog)
    except (ResolutionError, IntegrityError):
        oplog.emit(
            "build",
            actor=actor,
            stage="resolve",
            outcome="failed",
            source=source.hash[:8],
            latency_ms=round((time.monotonic() - started) * 1000, 3),
        )
        raise


def _resolve_refs(source: SourceSpec, backend: StoreBackend, oplog: OpLog) -> dict[str, str]:
    try:
        parsed = yaml.safe_load(source.yaml_raw)
    except yaml.YAMLError as error:
        raise ResolutionError(f"source is not valid YAML: {error}") from error

    if not isinstance(parsed, dict) or not isinstance(parsed.get("components"), list):
        raise ResolutionError("source must be a mapping with a `components` list")

    # ── capability gating, stage 1 (CLE need: a candidate can match an
    # intent semantically yet lack the capability the task requires — it
    # must fail HERE, fast, before anything is consumed, not silently
    # episode-by-episode at replay).
    declared_tools = parsed.get("tools", []) or []
    if not isinstance(declared_tools, list) or any(not isinstance(t, str) for t in declared_tools):
        raise ResolutionError("`tools` must be a list of tool names")
    for tool_name in declared_tools:
        target = _look_up(f"#tools/{tool_name}", backend)
        if target is None:
            raise ResolutionError(
                f"unresolved tool {tool_name}", missing_refs=(f"#tools/{tool_name}",)
            )
        record = json.loads(fetch_verified(backend, target, oplog))
        if record.get("kind") != "tool":
            raise ResolutionError(f"unresolved tool {tool_name}: ref is not a tool declaration")
    # Mount coverage: every capability the trigger says the cluster needs
    # must be declared. The detector writes trigger.requires_tools from the
    # cluster's observed requires_tool decor.
    trigger_raw = parsed.get("trigger") or {}
    required = trigger_raw.get("requires_tools", []) if isinstance(trigger_raw, dict) else []
    unmounted = sorted(set(required) - set(declared_tools))
    if unmounted:
        raise ResolutionError(
            f"tool required by trigger not mounted: {', '.join(unmounted)}",
            missing_refs=tuple(f"#tools/{t}" for t in unmounted),
        )

    component_refs = parsed["components"]
    malformed = [ref for ref in component_refs if not isinstance(ref, str) or not ref.startswith("#")]
    if malformed:
        raise ResolutionError(f"components must be `#ref` strings, got: {malformed}")

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for ref in component_refs:
        target_hash = _look_up(ref, backend)
        if target_hash is None:
            missing.append(ref)
            continue
        # Verify the component exists and re-hashes to its address before
        # the build may depend on it (integrity on read, cle-core-contracts).
        try:
            fetch_verified(backend, target_hash, oplog)
        except KeyError:
            # Dangling ref: name exists, object gone. (On InMemoryStore a
            # KeyError can only come from the first get; a backend where
            # the refetch can also miss — concurrent deletion — would be
            # misclassified here and needs tightening when Weaviate lands.)
            missing.append(ref)
            continue
        resolved[ref] = target_hash

    if missing:
        raise ResolutionError(
            f"unresolved refs: {sorted(missing)}", missing_refs=tuple(sorted(missing))
        )
    return resolved


def _look_up(ref: str, backend: StoreBackend) -> str | None:
    name = ref[1:]  # strip the leading '#'
    if _HASH_REF.match(ref):
        return name
    exact = [target for ref_name, target in backend.list_refs(name) if ref_name == name]
    return exact[0] if exact else None
