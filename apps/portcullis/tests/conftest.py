from __future__ import annotations


import asyncio
import json
import shutil
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from src.citadel_auth.testing import make_stack
from src.services import service_auth
from tests.auth_helpers import requester
from fastapi.testclient import TestClient

from src.app import create_app
from src.db import Database
from src.services.migrations import MigrationRunner
from src.config import BackupSettings, SecuritySettings, Settings
from src.services import otp_service
from src.services.caller import Caller
from src.services.email_service import EmailDeliveryError
from src.services.server_tools import ServerUnavailable
from src.services.traffic import TrafficRecorder
from tests.fake_turns import FakeTurns
from tests.fake_chats import FakeChats

ADMIN_USERNAME = "root"
ADMIN_PASSWORD = "correct horse battery"


@dataclass
class FakeEmailSender:
    """Records what would have been emailed; `fail` simulates SMTP being down."""

    sent: list[tuple[str, str, str]] = field(default_factory=list)  # (kind, to, code)
    fail: bool = False

    async def send_invite(self, to: str, code: str, expires_at: datetime) -> None:
        self._record("invite", to, code)

    async def send_email_verification(self, to: str, code: str, expires_at: datetime) -> None:
        self._record("verify", to, code)

    async def send_notification(self, to: str, subject: str, body: str) -> None:
        self._record("notification", to, f"{subject}\n\n{body}")

    def _record(self, kind: str, to: str, code: str) -> None:
        if self.fail:
            raise EmailDeliveryError("SMTP is down (fake)")
        self.sent.append((kind, to, code))

    def last_code(self, kind: str) -> str:
        return next(code for k, _to, code in reversed(self.sent) if k == kind)


AGENTS = [
    {"id": "claude-agent", "label": "Claude Agent", "url": "http://agent-a.internal/mcp"},
    {"id": "openai-agent", "label": "OpenAI Agent", "url": "http://agent-b.internal/mcp"},
]
MCP_SERVER_URL = "http://mcp-server.internal/mcp"


@dataclass
class FakeUsage:
    """Stronghold's /usage routes, simply: rows by account uid. `six_hour_limit` blocks `/usage/check`
    once an account has used that many tokens (0 = never); `down` makes every call a 503."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    six_hour_limit: int = 0
    down: bool = False

    def respond(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(503, json={"detail": "Storage is unavailable"})
        uid = requester(request)["sub"]
        path, mine = request.url.path, [row for row in self.rows if row["owner"] == uid]
        if path == "/usage/check":
            used = sum(row["total_tokens"] for row in mine)
            block = {"reason": "6-hour token limit reached", "reset_at": (datetime.now() + timedelta(hours=1)).isoformat()}
            return httpx.Response(200, json={"block": block if self.six_hour_limit and used >= self.six_hour_limit else None})
        if path == "/usage/records" and request.method == "POST":
            body = json.loads(request.content)
            for row in body["rows"]:
                self.rows.append({**row, "owner": uid, "turn_id": body["turn_id"], "kind": body["kind"],
                                  "chat_id": body["chat_id"], "created_at": datetime.now().isoformat(), "id": len(self.rows) + 1})
            return httpx.Response(201, json={"total": sum(row["total_tokens"] for row in body["rows"])})
        if path == "/usage/records":
            return httpx.Response(200, json=list(reversed(mine)))
        if path == "/usage":
            used = sum(row["total_tokens"] for row in mine)
            by_agent: dict[tuple, int] = {}
            for row in mine:
                key = (row.get("agent") or "unknown", row.get("model") or "")
                by_agent[key] = by_agent.get(key, 0) + row["total_tokens"]
            report = {
                "total_tokens": used, "summary_tokens": sum(r["total_tokens"] for r in mine if r["kind"] == "summary"),
                "turns": len({r["turn_id"] for r in mine if r["kind"] != "summary"}), "chats": len({r["chat_id"] for r in mine if r["chat_id"]}),
                "by_agent": [{"agent": a, "model": m, "tokens": t, "cost": None} for (a, m), t in by_agent.items()],
                "daily": [{"date": datetime.now().date().isoformat(), "tokens": used}] if used else [],
            }
            return httpx.Response(200, json={
                "six_hour": {"used": used, "limit": self.six_hour_limit, "reset_at": None},
                "weekly": {"used": used, "limit": 5_000_000, "reset_at": None}, "report": report})
        if path == "/usage/all":
            totals: dict[str, dict[str, Any]] = {}
            for row in self.rows:
                entry = totals.setdefault(row["owner"], {"uid": row["owner"], "tokens": 0, "turn_ids": set(), "last_used_at": None})
                entry["tokens"] += row["total_tokens"]
                entry["turn_ids"] |= {row["turn_id"]} if row["kind"] != "summary" else set()
                entry["last_used_at"] = row["created_at"]
            return httpx.Response(200, json=[{"uid": e["uid"], "tokens": e["tokens"], "turns": len(e["turn_ids"]),
                                             "last_used_at": e["last_used_at"]} for e in totals.values()])
        if request.method == "DELETE" and path.startswith("/usage/accounts/"):
            self.rows[:] = [row for row in self.rows if row["owner"] != path.rsplit("/", 1)[1]]
            return httpx.Response(204)
        return httpx.Response(404, json={"detail": "Not found"})


@dataclass
class FakeUpstream:
    """Stands in for ai_agent/mcp_server behind the proxy. Records every
    request it gets; `handler` decides the response (default: an empty
    JSON-RPC result carrying a session id)."""

    requests: list[httpx.Request] = field(default_factory=list)
    handler: Callable[[httpx.Request], httpx.Response] | None = None
    unreachable: bool = False
    # Answers Stronghold's /usage routes whatever `handler` is; set to None to let `handler` answer them.
    usage: FakeUsage | None = field(default_factory=FakeUsage)
    # Answers Stronghold's /chats and /chat-folders routes the same way; None lets `handler` answer them.
    chats: FakeChats | None = field(default_factory=FakeChats)
    # Answers Stronghold's /turns routes; None lets `handler` answer them.
    turns: FakeTurns | None = field(default_factory=FakeTurns)
    # Stronghold's answer to "may this account write to its brain?" when `handler` does not take /brains/writable.
    brain_writable: bool = True
    # Stronghold's answers when a turn starts: the agents the account switched off, and its private extensions.
    disabled_agents: list = field(default_factory=list)
    agents_status: int = 200
    agents_fake: bool = True  # False: `handler` answers /account-agents too (pass-through tests)
    private: dict = field(default_factory=lambda: {"items": [], "skipped": []})
    private_status: int = 200

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        self.requests.append(request)
        if self.unreachable:
            raise httpx.ConnectError("connection refused (fake)", request=request)
        if self.usage is not None and request.url.path.startswith("/usage"):
            return self.usage.respond(request)
        if self.turns is not None and request.url.path.startswith("/turns"):
            return self.turns.respond(request)
        if self.chats is not None and request.url.path.startswith(("/chats", "/chat-folders")):
            return self.chats.respond(request)
        if self.agents_fake and request.url.path == "/account-agents" and request.method == "GET":
            return httpx.Response(self.agents_status, json={"disabled": self.disabled_agents})
        if request.url.path == "/user-extensions/for-turn":
            return httpx.Response(self.private_status, json=self.private)
        if request.url.path.startswith("/brains/writable/"):
            return httpx.Response(200, json={"writable": self.brain_writable})
        if self.handler:
            return self.handler(request)
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": {}}, headers={"mcp-session-id": "sess-1"}
        )


@dataclass
class FakeServerTools:
    """Stands in for portcullis's own MCP client to mcp_server."""

    unreachable: bool = False
    callers: list[Caller] = field(default_factory=list)
    # options_url templates the fake's tools declare.
    templates: set[str] = field(default_factory=set)

    async def options_templates(self, caller: Caller) -> set[str]:
        self.callers.append(caller)
        if self.unreachable:
            raise ServerUnavailable("connection refused (fake)")
        return set(self.templates)


class FakeDbGateway:
    """In-memory DocumentStore: same behaviour as db_gateway for get/put/delete/query."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict] = {}
        self.instances_seen = {"portcullis": ["main"], "stronghold": ["stronghold"]}
        self.admin_calls: list[tuple] = []

    async def instances(self):
        return self.instances_seen

    async def admin(self, method, path, body=None):
        """Treasury's /admin routes: remembers the calls; a refusal is staged with `admin_refusal`."""
        from src.services.db_gateway import DbGatewayRefused

        self.admin_calls.append((method, path, body))
        if getattr(self, "admin_refusal", None):
            raise DbGatewayRefused(400, self.admin_refusal)
        if path.startswith("/admin/services"):
            return {"services": []}
        return {"connections": [], "default_cache": {}, "applies": "now"}

    async def set_instance(self, name, connections):
        self.instances_seen[name] = list(connections)

    async def delete_instance(self, name):
        self.instances_seen.pop(name, None)

    async def get(self, collection, key):
        doc = self.records.get((collection, key))
        return None if doc is None else json.loads(json.dumps(doc))

    async def put(self, collection, key, doc):
        self.records[(collection, key)] = json.loads(json.dumps(doc))

    async def create(self, collection, key, doc):
        if (collection, key) in self.records:
            return False
        self.records[(collection, key)] = json.loads(json.dumps(doc))
        return True

    async def delete(self, collection, key):
        return self.records.pop((collection, key), None) is not None

    async def query(self, collection, filters=None, limit=100, offset=0):
        rows = sorted((k, d) for (c, k), d in self.records.items() if c == collection)
        matching = [d for _, d in rows if all(d.get(f) == v for f, v in (filters or {}).items())]
        return json.loads(json.dumps(matching[offset : offset + limit]))  # copies, like a real HTTP answer


_MIGRATED_TEMPLATE: Path | None = None


def migrated_database() -> Path:
    """One migrated, empty database per test session. Every test app copies it, so its start finds the
    database already current and skips the migrations (about 0.4 s a test). Tests of the migrations
    themselves build their own database."""
    global _MIGRATED_TEMPLATE
    if _MIGRATED_TEMPLATE is None:
        path = Path(tempfile.mkdtemp(prefix="portcullis-template-")) / "template.db"

        async def build() -> None:
            database = Database(f"sqlite+aiosqlite:///{path.as_posix()}")
            await MigrationRunner(database.engine).run()
            await database.engine.dispose()

        asyncio.run(build())
        _MIGRATED_TEMPLATE = path
    return _MIGRATED_TEMPLATE


def make_settings(
    tmp_path: Path,
    *,
    admin_password: str = ADMIN_PASSWORD,
    session_hours: int = 12,
    security: SecuritySettings | None = None,
    backup: BackupSettings | None = None,
    require_email_verification: bool = True,
) -> Settings:
    registry = tmp_path / "config_agents.json"
    registry.write_text(json.dumps({"agents": AGENTS}), encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text(
        f"BOOTSTRAP_ADMIN_USERNAME={ADMIN_USERNAME}\n"
        "BOOTSTRAP_ADMIN_EMAIL=root@example.com\n"
        f"BOOTSTRAP_ADMIN_PASSWORD={admin_password}\n",
        encoding="utf-8",
    )
    database_path = tmp_path / "data" / "test.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if not database_path.exists():  # a second app in one test shares the first one's database
        shutil.copyfile(migrated_database(), database_path)
    return Settings(
        host="127.0.0.1",
        port=0,
        database_path=database_path,
        session_cookie_name="ember_session",
        session_hours=session_hours,
        cookie_secure=False,  # TestClient talks plain http
        require_email_verification=require_email_verification,
        env_path=env_path,
        agents_registry_path=registry,
        security=security or SecuritySettings(),
        # Off unless a test asks: a background copy of every test's database is noise.
        backup=backup or BackupSettings(enabled=False),
        config_path=tmp_path / "config_app.json",
    )


@pytest.fixture(autouse=True)
def no_verification_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests send verification emails back to back; the cooldown itself is tested in
    test_verification_limits.py, which puts it back."""
    monkeypatch.setattr(otp_service, "VERIFICATION_COOLDOWN", timedelta(0))


@pytest.fixture
def email() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def upstream() -> FakeUpstream:
    return FakeUpstream()


@pytest.fixture
def server_tools() -> FakeServerTools:
    return FakeServerTools()


@pytest.fixture
def db_gateway() -> FakeDbGateway:
    return FakeDbGateway()


@pytest.fixture
def traffic() -> TrafficRecorder:
    """Counts in memory only (no database), so tests read it with pending()."""
    return TrafficRecorder()


@pytest.fixture
def client_factory(
    tmp_path: Path,
    email: FakeEmailSender,
    upstream: FakeUpstream,
    server_tools: FakeServerTools,
    traffic: TrafficRecorder,
    db_gateway: FakeDbGateway,
) -> Iterator[Callable[..., TestClient]]:
    """Builds a started app (lifespan run) per call; all are closed at the end."""
    opened: list[TestClient] = []

    def factory(address: str = "testclient", **kwargs) -> TestClient:
        """address: the socket peer the app sees (default: Starlette's
        "testclient"), for tests that depend on the client IP."""
        client = TestClient(
            create_app(
                make_settings(tmp_path, **kwargs),
                email_sender=email,
                upstream_transport=httpx.MockTransport(upstream),
                server_tools=server_tools,
                traffic=traffic,
                db_gateway=db_gateway,
            ),
            client=(address, 50000),
        )
        client.__enter__()
        client.app.state.catalog._known["armory"] = "http://mcp-server.internal"
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def client(client_factory) -> TestClient:
    return client_factory()

@pytest.fixture(scope="session")
def auth_stack(tmp_path_factory):
    return asyncio.run(make_stack(tmp_path_factory.mktemp("auth")))


@pytest.fixture(autouse=True)
def service_identity(monkeypatch, auth_stack):
    monkeypatch.setattr(service_auth, "keyring", auth_stack["portcullis"])
    service_auth._cache.clear()

