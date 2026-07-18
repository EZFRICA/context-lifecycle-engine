"""Mount scopes (ro/rw) and MCP handles.

CLE need: a promoted agent gets exactly the context and tool scopes its
evidence justifies, per workspace (BLUEPRINT §1 runtime scope). A mount
names a scope and a mode; nothing an agent was not mounted with exists
for it.

Decisions (P2, documented per authorization):
- MCP handles are network mounts: scope_ref `mcp://<server>/<tool>`. They
  are not store-resolvable, so store validation skips them; mode still
  applies (an ro MCP mount is a read-only tool surface).
- rw store mounts must target MOBILE ref names — a raw content hash or an
  immutable version ref cannot absorb a write (content addresses don't
  move; version refs must not).
- ALL store mounts (ro included) must resolve at instantiation: a dead ro
  mount is a broken context, not a lesser error.
"""

import re
from typing import Literal

from pydantic import BaseModel

from cle.store.backends import StoreBackend

_MCP_SCHEME = "mcp://"
_RAW_HASH = re.compile(r"^[0-9a-f]{64}$")
_VERSION_REF = re.compile(r"^agents/.+/v\d+\.\d+\.\d+$")


class MountError(Exception):
    """A mount that cannot be honored fails instantiation before any
    container exists — scopes are contracts, not suggestions."""


class Mount(BaseModel, frozen=True):
    scope_ref: str
    mode: Literal["ro", "rw"]

    @property
    def is_mcp(self) -> bool:
        return self.scope_ref.startswith(_MCP_SCHEME)


def validate_mounts(mounts: list[Mount], backend: StoreBackend) -> None:
    """Every store mount must resolve; rw mounts must be writable targets."""
    for mount in mounts:
        if mount.is_mcp:
            continue
        if _RAW_HASH.match(mount.scope_ref):
            if mount.mode == "rw":
                raise MountError(
                    f"rw mount {mount.scope_ref[:8]} targets a content address; "
                    "writes need a mobile ref"
                )
            try:
                backend.get(mount.scope_ref)
            except KeyError:
                raise MountError(f"mount object {mount.scope_ref[:8]} not in store") from None
            continue
        if mount.mode == "rw" and _VERSION_REF.match(mount.scope_ref):
            raise MountError(f"rw mount {mount.scope_ref} targets an immutable version ref")
        resolved = [t for name, t in backend.list_refs(mount.scope_ref) if name == mount.scope_ref]
        if not resolved:
            raise MountError(f"mount ref {mount.scope_ref} not in store")


def as_record(mounts: list[Mount]) -> dict[str, str]:
    """The data-only shape the Container record carries (scope_ref -> mode);
    the Mount model itself stays runtime-side."""
    return {mount.scope_ref: mount.mode for mount in mounts}
