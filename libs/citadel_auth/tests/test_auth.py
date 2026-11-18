"""Security contracts for service and requester authentication."""

import asyncio
import os
import stat
import time
import uuid

import httpx
import jwt
import pytest

from citadel_auth import (
    AuthError, Keyring, ServiceAuth, ServiceAuthMiddleware, current_caller,
    current_requester, mint_requester, sign_assertion, verify_assertion, verify_requester,
)
from citadel_auth.policy import allowed, may_forward
from citadel_auth.testing import make_stack


@pytest.fixture
async def stack(tmp_path):
    return await make_stack(tmp_path, services=["portcullis", "stronghold", "legion", "armory", "treasury"])


async def test_concurrent_process_identities_never_read_partial_private_key(tmp_path, monkeypatch):
    """Independent Legion keyrings can start together against one identity mount."""
    from pathlib import Path
    original = os.open
    final = tmp_path / "identity" / "key.pem"

    def slow_create(path, flags, mode=0o777, **kwargs):
        descriptor = original(path, flags, mode, **kwargs)
        if Path(path) == final and flags & os.O_CREAT:
            time.sleep(0.05)  # Expose any premature publication before its writer fills the file.
        return descriptor

    monkeypatch.setattr(os, "open", slow_create)
    rings = [Keyring("legion", tmp_path / "trust", final.parent) for _ in range(16)]
    await asyncio.gather(*(ring.ensure_identity() for ring in rings))
    assert len({ring.kid for ring in rings}) == 1


async def test_sign_verify_and_replay(stack):
    assertion = sign_assertion(stack["stronghold"], "armory")
    assert (await verify_assertion(stack["armory"], assertion, "armory")).name == "stronghold"
    with pytest.raises(AuthError, match="replay"):
        await verify_assertion(stack["armory"], assertion, "armory")


@pytest.mark.parametrize("mutation,cause", [
    ({"exp": 1, "iat": -59}, "expired"),
    ({"aud": "legion"}, "audience"),
    ({"iat": 9999999999, "exp": 10000000059}, "skew"),
    ({"iss": "unknown"}, "unknown caller"),
    ({"iss": "legion"}, "key id"),
    ({"exp": 9999999999}, "lifetime"),
    ({"jti": ""}, "claims"),
    ({"typ": "requester"}, "type"),
])
async def test_reject_invalid_claims(stack, mutation, cause):
    keyring = stack["stronghold"]
    now = int(time.time())
    claims = {"iss": "stronghold", "aud": "armory", "iat": now, "exp": now + 60, "jti": uuid.uuid4().hex}
    claims.update(mutation)
    token = jwt.encode(claims, keyring.private_key, algorithm="EdDSA", headers={"kid": keyring.kid})
    with pytest.raises(AuthError, match=cause):
        await verify_assertion(stack["armory"], token, "armory")


async def test_wrong_key_and_tampered_claims(stack, tmp_path):
    impostor = Keyring("stronghold", tmp_path / "elsewhere", tmp_path / "impostor")
    await impostor.ensure_identity()
    with pytest.raises(AuthError):
        await verify_assertion(stack["armory"], sign_assertion(impostor, "armory"), "armory")
    token = sign_assertion(stack["stronghold"], "armory")
    header, payload, signature = token.split(".")
    payload = jwt.utils.base64url_encode(b'{"iss":"portcullis","aud":"armory"}').decode()
    with pytest.raises(AuthError):
        await verify_assertion(stack["armory"], f"{header}.{payload}.{signature}", "armory")


async def test_unknown_kid_reloads_owner_key(stack, tmp_path):
    receiver = stack["armory"]
    await verify_assertion(receiver, sign_assertion(stack["stronghold"], "armory"), "armory")
    rotated = Keyring("stronghold", stack["stronghold"].trust_dir, tmp_path / "new-identity")
    await rotated.ensure_identity()
    assert (await verify_assertion(receiver, sign_assertion(rotated, "armory"), "armory")).name == "stronghold"


async def test_private_identity_not_published(stack):
    owner = stack["stronghold"]
    assert {path.name for path in (owner.trust_dir / "stronghold").iterdir()} == {"key.pub"}
    if os.name != "nt":
        assert stat.S_IMODE((owner.identity_dir / "key.pem").stat().st_mode) == 0o600
    await owner.ensure_identity()
    assert (await verify_assertion(stack["armory"], sign_assertion(owner, "armory"), "armory")).name == "stronghold"


async def test_unreadable_trust_fails_closed(stack, monkeypatch):
    from pathlib import Path
    original = Path.read_bytes
    def unreadable(path):
        if path.name == "key.pub":
            raise PermissionError("test unreadable trust")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", unreadable)
    with pytest.raises(AuthError, match="trust"):
        await verify_assertion(stack["armory"], sign_assertion(stack["legion"], "armory"), "armory")


@pytest.mark.parametrize("audience,caller,path,forward", [
    ("stronghold", "portcullis", "/chat", True),
    ("stronghold", "armory", "/brains/resolve", True),
    ("armory", "portcullis", "/download/file", True),
    ("armory", "stronghold", "/notes", True),
    ("armory", "legion", "/mcp", True),
    ("legion", "portcullis", "/agents", True),
    ("legion", "stronghold", "/registry", True),
    ("legion", "armory", "/mcp", True),
    ("legion", "stronghold", "/agents/tuning", True),
    ("legion", "legion", "/mcp", True),
    ("armory", "portcullis", "/commands/help", True),
    ("armory", "portcullis", "/pdf/ui/files", True),
    ("armory", "portcullis", "/tickets/tags", True),
    ("armory", "stronghold", "/upload/pdf", True),
    ("armory", "stronghold", "/brains/operation", True),
    ("armory", "stronghold", "/brains/destination", True),
    ("armory", "portcullis", "/admin/brain", True),
    ("stronghold", "armory", "/brains/instance-migration", True),
    ("armory", "stronghold", "/ticket-admin/tickets", True),
    ("treasury", "portcullis", "/instances", False),
    ("treasury", "stronghold", "/instances", False),
    ("treasury", "legion", "/instances", False),
    ("treasury", "armory", "/instances", False),
    ("portcullis", "stronghold", "/internal/requester-token", False),
])
def test_policy_rows(audience, caller, path, forward):
    assert allowed(audience, caller, path)
    assert may_forward(audience, caller) == forward
    assert not allowed(audience, "unknown", path)


def test_policy_denies_unlisted_routes_and_prefix_lookalikes():
    assert not allowed("stronghold", "armory", "/brains/resolve-admin")
    assert not allowed("armory", "portcullis", "/brains/destination")
    assert not allowed("armory", "stronghold", "/admin/brain")
    assert not allowed("armory", "legion", "/admin")
    assert not allowed("portcullis", "stronghold", "/internal-evil")
    assert not allowed("armory", "treasury", "/mcp")


async def test_requester_only_portcullis_can_mint_and_sign(stack):
    token = mint_requester(stack["portcullis"], "uid-1", "alice", "alice@example.com", ["armory", "legion"])
    requester = await verify_requester(stack["armory"], token, "armory")
    assert (requester.uid, requester.username, requester.email) == ("uid-1", "alice", "alice@example.com")
    # A requester token may be forwarded repeatedly; service assertions may not.
    assert await verify_requester(stack["armory"], token, "armory") == requester
    with pytest.raises(AuthError):
        mint_requester(stack["legion"], "uid", "alice", "", ["armory"])
    claims = jwt.decode(token, options={"verify_signature": False})
    forged = jwt.encode(claims, stack["legion"].private_key, algorithm="EdDSA", headers={"kid": stack["legion"].kid})
    with pytest.raises(AuthError):
        await verify_requester(stack["armory"], forged, "armory")
    with pytest.raises(AuthError, match="audience"):
        await verify_requester(stack["stronghold"], token, "stronghold")
    with pytest.raises(AuthError):
        await verify_assertion(stack["armory"], token, "armory")


async def test_middleware_policy_requester_and_context_reset(stack):
    async def app(scope, receive, send):
        caller = current_caller()
        requester = current_requester()
        body = f"{caller.name if caller else ''}|{requester.uid if requester else ''}".encode()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body})
    middleware = ServiceAuthMiddleware(app, stack["armory"], "armory")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=middleware), base_url="http://armory") as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.post("/mcp")).status_code == 401
        token = mint_requester(stack["portcullis"], "real", "alice", "", ["armory"])
        response = await client.post("/mcp", headers={
            "Authorization": "Bearer " + sign_assertion(stack["legion"], "armory"),
            "X-Citadel-Requester": token, "X-Requester-Uid": "forged"})
        assert response.text == "legion|real"
        assert (await client.get("/admin", headers={"Authorization": "Bearer " + sign_assertion(stack["legion"], "armory")})).status_code == 403
        assert (await client.post("/mcp", headers={"Authorization": "Bearer " + sign_assertion(stack["treasury"], "armory")})).status_code == 403
        assert (await client.post("/mcp", headers={"Authorization": "Bearer " + sign_assertion(stack["legion"], "armory"), "X-Requester-Uid": "forged"})).text == "legion|"
    assert current_caller() is None
    assert current_requester() is None


async def test_service_auth_mints_unique_assertions_for_concurrent_requests(stack):
    received = []
    async def handle(request):
        caller = await verify_assertion(stack["armory"], request.headers["Authorization"][7:], "armory")
        received.append(caller.name)
        return httpx.Response(200)
    async with httpx.AsyncClient(auth=ServiceAuth(stack["legion"], "armory"), transport=httpx.MockTransport(handle)) as client:
        responses = await asyncio.gather(*(client.post("http://armory/mcp") for _ in range(20)))
    assert all(response.status_code == 200 for response in responses)
    assert received == ["legion"] * 20


def test_data_and_cache_live_under_the_citadel_root(tmp_path, monkeypatch):
    from citadel_auth import cache_dir, data_dir

    for name in ("CITADEL_DATA_DIR", "CITADEL_CACHE_DIR"):
        monkeypatch.delenv(name, raising=False)
    project = tmp_path / "apps" / "armory"
    project.mkdir(parents=True)
    assert data_dir(project) == (tmp_path / ".data" / "armory").resolve()
    assert cache_dir(project) == (tmp_path / ".cache" / "armory").resolve()
    (tmp_path / ".env").write_text(f"CITADEL_DATA_DIR=store\nCITADEL_CACHE_DIR='{tmp_path / 'elsewhere'}'\n", encoding="utf-8")
    assert data_dir(project) == (tmp_path / "store" / "armory").resolve()
    assert cache_dir(project) == tmp_path / "elsewhere" / "armory"
    monkeypatch.setenv("CITADEL_DATA_DIR", str(tmp_path / "env"))
    assert data_dir(project) == tmp_path / "env" / "armory"
    assert data_dir(tmp_path / "app") == (tmp_path / "app").resolve() / ".data"


def test_root_env_overrides_a_service_env(tmp_path, monkeypatch):
    from citadel_auth import root_overrides

    monkeypatch.delenv("CITADEL_ROOT_ENV", raising=False)
    monkeypatch.delenv("CITADEL_SERVICE", raising=False)
    armory = tmp_path / "apps" / "armory"
    legion = tmp_path / "apps" / "legion"
    for folder, names in ((armory, "TAVILY_API_KEY=\nBARD_TOKEN=\n"), (legion, "BARD_TOKEN=\n")):
        folder.mkdir(parents=True)
        (folder / ".env.example").write_text(names, encoding="utf-8")
    (tmp_path / ".env").write_text(
        "TAVILY_API_KEY=plain\nBARD_TOKEN=shared\nARMORY__BARD_TOKEN=armory-only\nGATEWAY_ADMIN_PASSWORD=secret\nLEGION__EMPTY=\n",
        encoding="utf-8")
    assert root_overrides(armory) == {"TAVILY_API_KEY": "plain", "BARD_TOKEN": "armory-only"}
    assert root_overrides(legion) == {"BARD_TOKEN": "shared"}
    assert root_overrides(tmp_path / "other") == {}
