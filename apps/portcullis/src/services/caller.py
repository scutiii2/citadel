"""Who a call is made for; sent as the identity headers of the proxy and the server tools."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Caller:
    username: str
    email: str
    uid: str = ""
    brain_scope: str = ""
