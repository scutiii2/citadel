"""Requester identity comes only from a verified Portcullis-signed token."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from src.citadel_auth import current_requester as verified_requester


@dataclass(frozen=True)
class Requester:
    """The account a request is made for. `uid` never changes; data is keyed on it."""

    uid: str
    username: str
    email: str


async def current_requester() -> Requester:
    """Only a Portcullis-signed requester identifies an account."""
    who = verified_requester()
    if who is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing requester identity")
    return Requester(uid=who.uid, username=who.username, email=who.email)
