"""Requester renewal never forwards expired credentials and fails closed."""
import asyncio
import time
import uuid

import jwt
import pytest

from src.citadel_auth import AuthError, mint_requester
from src.citadel_auth.testing import make_stack
from src.turns.requester_tokens import RequesterRenewal, RequesterRefreshError


@pytest.fixture
async def credentials(tmp_path):
    stack = await make_stack(tmp_path)
    now = int(time.time())
    claims = {"typ": "requester", "iss": "portcullis", "sub": "uid", "username": "alice", "email": "",
              "aud": ["stronghold", "legion", "armory"], "iat": now - 850, "exp": now + 50, "jti": uuid.uuid4().hex}
    old = jwt.encode(claims, stack["portcullis"].private_key, algorithm="EdDSA", headers={"kid": stack["portcullis"].kid})
    fresh = mint_requester(stack["portcullis"], "uid", "alice", "", claims["aud"])
    return stack, old, fresh


async def test_refreshes_before_expiry_and_forwards_only_fresh_token(credentials):
    stack, old, fresh = credentials
    calls = []
    async def refresh(uid):
        calls.append(uid)
        return fresh
    renewal = RequesterRenewal(stack["stronghold"], "uid", old, refresh)
    await renewal.renew_if_needed()
    assert calls == ["uid"]
    assert renewal.token() == fresh
    await renewal.renew_if_needed()
    assert calls == ["uid"]


async def test_refresh_refusal_interrupts_running_operation(credentials):
    stack, old, _ = credentials
    stopped = asyncio.Event()
    async def refresh(uid):
        raise RuntimeError("refused")
    async def operation():
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
    renewal = RequesterRenewal(stack["stronghold"], "uid", old, refresh)
    with pytest.raises(RequesterRefreshError, match="interrupted"):
        await renewal.run(operation())
    assert stopped.is_set()


async def test_expired_token_never_returned(credentials):
    stack, old, fresh = credentials
    renewal = RequesterRenewal(stack["stronghold"], "uid", old, lambda uid: asyncio.sleep(0, result=fresh),
                               clock=lambda: time.time() + 51)
    with pytest.raises(RequesterRefreshError, match="expired"):
        renewal.token()


async def test_refresh_cannot_change_requester(credentials):
    stack, old, _ = credentials
    other = mint_requester(stack["portcullis"], "other", "other", "", ["stronghold", "legion", "armory"])
    renewal = RequesterRenewal(stack["stronghold"], "uid", old, lambda uid: asyncio.sleep(0, result=other))
    with pytest.raises(RequesterRefreshError):
        await renewal.renew_if_needed()
