"""Who is asking. Portcullis authenticates the account and sends its identity in
headers; Stronghold trusts them because the internal token was already checked."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class Requester:
    """The account a request is made for. `uid` never changes; data is keyed on it."""

    uid: str
    username: str
    email: str


async def current_requester(
    x_requester_uid: str = Header(""),
    x_requester_username: str = Header(""),
    x_requester_email: str = Header(""),
) -> Requester:
    """The requester from Portcullis's headers, or 400 when the uid is missing."""
    if not x_requester_uid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing requester identity")
    return Requester(uid=x_requester_uid, username=x_requester_username, email=x_requester_email)
