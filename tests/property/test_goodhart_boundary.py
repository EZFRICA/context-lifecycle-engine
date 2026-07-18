"""Invariant 2 — the Goodhart boundary, enforced by reflection.

Container must expose NO read path to its own metrics: no method, no
property, no injected context. This test is written against the P1 stub and
must stay green through P2's runtime work — any widening of the Container
surface fails here before it reaches review.
"""

import inspect

from pydantic import BaseModel

from cle.runtime.container import Container

# The complete allowed public surface of the Container record. Adding ANY
# public field, method, or property requires amending this set — which is
# exactly the review conversation the invariant wants to force.
ALLOWED_PUBLIC_FIELDS = {"image_hash", "workspace_id", "mounts", "metrics_volume_id"}


def _public_members(cls: type) -> set[str]:
    return {name for name in dir(cls) if not name.startswith("_")}


def test_container_fields_are_exactly_the_declared_record() -> None:
    assert set(Container.model_fields) == ALLOWED_PUBLIC_FIELDS


def test_container_adds_no_public_surface_beyond_pydantic() -> None:
    # Everything public on Container must be either a declared record field
    # or plain BaseModel machinery — no extra methods or properties where a
    # metrics read path could hide.
    extra_surface = _public_members(Container) - _public_members(BaseModel) - ALLOWED_PUBLIC_FIELDS
    assert not extra_surface, f"Container grew a public surface: {extra_surface}"


def test_container_defines_no_properties_or_methods_of_its_own() -> None:
    # Belt and braces: even a member shadowing a BaseModel name would show
    # up in the class __dict__; only pydantic's model_config/fields
    # bookkeeping and annotations may live there.
    own_callables = {
        name
        for name, member in vars(Container).items()
        if not name.startswith("_") and (callable(member) or isinstance(member, property))
    }
    assert not own_callables, f"Container defines its own callables: {own_callables}"


def test_metrics_reference_is_an_opaque_id_only() -> None:
    # The single metrics-adjacent member is the volume id the runtime
    # writes to — a plain str, not a structure something could read from.
    # (pydantic v2 keeps fields off the class dir(), so sweep both the
    # class surface and the declared fields.)
    full_surface = _public_members(Container) | set(Container.model_fields)
    metric_named = {name for name in full_surface if "metric" in name.lower()}
    assert metric_named == {"metrics_volume_id"}
    assert Container.model_fields["metrics_volume_id"].annotation is str


def test_container_instances_hold_no_metrics_objects() -> None:
    container = Container(
        image_hash="deadbeef" * 8,
        workspace_id="ws-1",
        mounts={"notes": "ro"},
        metrics_volume_id="vol-1",
    )
    for field_name in ALLOWED_PUBLIC_FIELDS:
        value = getattr(container, field_name)
        # No field value may be (or contain) anything with record/read
        # behavior; the record is data-only.
        assert not inspect.ismethod(value) and not callable(value)
