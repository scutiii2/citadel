"""Shared fixtures. Tests never read the real .env, the shared token file, Treasury or Portcullis."""

import json
import os


import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from src.citadel_auth import ServiceAuth
from src.tool_services.store import ToolStore
from tests import auth_helpers
from tests.auth_helpers import identity, service_auth

IDENTITY = {
    "uid": "u-1", "username": "ana", "email": "ana@example.com",
}


@pytest.fixture(scope="session")
def auth_stack(tmp_path_factory):
    import asyncio
    from src.citadel_auth.testing import make_stack
    auth_helpers.stack = asyncio.run(make_stack(tmp_path_factory.mktemp("service-auth")))
    return auth_helpers.stack


@pytest.fixture(autouse=True)
def service_identity(auth_stack, monkeypatch):
    from src import service_auth as wiring
    monkeypatch.setattr(wiring, "keyring", auth_stack["stronghold"])


class FakeDbGateway:
    """In-memory DocumentStore: same behaviour as Treasury for get/put/delete/query.

    A collection missing from src/schema/catalog.py is refused, so new storage cannot skip the catalog.
    The schema state lives in `system`, apart from `records`, which tests compare as the account data."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict] = {}
        self.system: dict[tuple[str, str], dict] = {}

    def _table(self, collection):
        from src.schema.catalog import BY_NAME, STATE

        assert collection in BY_NAME, f"collection {collection!r} is not in src/schema/catalog.py"
        return self.system if collection == STATE else self.records

    async def get(self, collection, key):
        doc = self._table(collection).get((collection, key))
        return None if doc is None else json.loads(json.dumps(doc))

    async def put(self, collection, key, doc):
        self._table(collection)[(collection, key)] = json.loads(json.dumps(doc))

    async def create(self, collection, key, doc):
        table = self._table(collection)
        if (collection, key) in table:
            return False
        table[(collection, key)] = json.loads(json.dumps(doc))
        return True

    async def delete(self, collection, key):
        return self._table(collection).pop((collection, key), None) is not None

    async def query(self, collection, filters=None, limit=100, offset=0):
        rows = sorted((k, d) for (c, k), d in self._table(collection).items() if c == collection)
        matching = [d for _, d in rows if all(d.get(f) == v for f, v in (filters or {}).items())]
        return json.loads(json.dumps(matching[offset : offset + limit]))  # copies, like a real HTTP answer


class FakePlatform:
    """Portcullis as Stronghold sees it: every account is a recipient, every switch is on."""

    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []
        self.actions: list[tuple[str, str, str]] = []
        self.logs: list[dict] = []
        # What each account may do; `granted[uid] = None` is an inactive or unverified account.
        self.default_permissions = {"chat.use", "settings.manage", "tools.execute"}
        self.granted: dict[str, set[str] | None] = {}
        self.usernames = {"bob": "u-2", "cyd": "u-3"}

    async def permissions(self, uid):
        return self.granted.get(uid, self.default_permissions)

    async def uid_for_username(self, username):
        uid = self.usernames.get(username)
        if uid is None or uid in self.granted and self.granted[uid] is None:
            return None
        return uid, username

    async def requester_token(self, uid):
        return identity(uid=uid)["X-Citadel-Requester"]

    async def log_action(self, uid, action, message):
        self.actions.append((uid, action, message))

    async def write_log(self, kind, uid, source, message, details=None, prompts=None):
        self.logs.append({"kind": kind, "uid": uid, "source": source, "message": message, "details": details, "prompts": prompts})

    async def report_error(self, source, message):
        self.errors.append((source, message))


@pytest.fixture
def db_gateway() -> FakeDbGateway:
    return FakeDbGateway()


AGENTS = [
    {"id": "claude-agent", "label": "Claude Agent", "url": "http://agent-a.internal/mcp"},
    {"id": "openai-agent", "label": "OpenAI Agent", "url": "http://agent-b.internal/mcp"},
]


class FakeAgent:
    """Stands in for Legion behind the AgentGateway: `summary` is what interpret() answers,
    `fail` makes a call fail, and tests replace `ask` when they need one."""

    def __init__(self) -> None:
        self.summary = "SUMMARY"
        self.fail: str | None = None
        self.interprets: list[str] = []
        self.probes: list[dict] = []
        self.probe_results: dict = {}
        self.probe_fail: str | None = None

    async def ask(self, url, caller, **kwargs):
        raise AssertionError("this test did not expect an ask() call")

    async def interpret(self, url, caller, text):
        from src.agents.gateway import AgentCallError

        self.interprets.append(text)
        if self.fail:
            raise AgentCallError(self.fail)
        return {"response": self.summary, "provider_id": "claude", "model": "claude-test", "total_tokens": 10}

    async def probe_extension(self, url, caller, *, extension_url, headers):
        from src.agents.gateway import AgentCallError

        self.probes.append({"url": url, "caller": caller, "extension_url": extension_url, "headers": headers})
        if self.probe_fail:
            raise AgentCallError(self.probe_fail)
        return self.probe_results.get(extension_url, {"status": "connected", "error": None, "tools": ["add", "search"]})


@pytest.fixture
def agent() -> FakeAgent:
    return FakeAgent()


class FakeArmory:
    """Armory's HTTP routes: `handler` answers, `requests` records."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.handler = lambda request: httpx.Response(200, json=[])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


@pytest.fixture
def armory() -> FakeArmory:
    return FakeArmory()


@pytest.fixture
def legion() -> FakeArmory:
    """Legion's /agents/tuning route: `handler` answers, `requests` records."""
    return FakeArmory()


@pytest.fixture
def tools() -> dict[str, FakeArmory]:
    """Each outside tool service has its own recording HTTP handler."""
    return {name: FakeArmory() for name in ("scribe", "reader", "bard")}


TOOL_TOKEN = "fake-tool-token"
TOOL_ORIGINS = {name: f"http://{name}.test" for name in ("bard", "scribe", "reader")}
TOOL_ORIGINS["o1"] = TOOL_ORIGINS["bard"]


def tool_options(settings, tools, *, seed_store=True):
    if seed_store:
        store = ToolStore(settings.data_dir / "settings.db")
        for name in tools:
            store.put(name, {"enabled": True, "service_id": name, "token": TOOL_TOKEN, "origins": [{"origin_id": name}]})

    def dispatch(request: httpx.Request) -> httpx.Response:
        return tools[request.url.host.split(".")[0]](request)

    return {"tool_http": httpx.AsyncClient(transport=httpx.MockTransport(dispatch)),
            "tool_origins": TOOL_ORIGINS.__getitem__}


def mock_tool_catalog(app, monkeypatch):
    async def refresh():
        return True

    monkeypatch.setattr(app.state.catalog, "outside_origin", TOOL_ORIGINS.__getitem__)
    monkeypatch.setattr(app.state.catalog, "refresh", refresh)


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform()


@pytest.fixture
def client(tmp_path, db_gateway, armory, platform, agent, tools, legion, monkeypatch):
    """The app with its lifespan running, an open token and the requester headers already set."""
    from src.api import create_app
    from src.config import Settings

    upstream = httpx.AsyncClient(base_url="http://armory.test", transport=httpx.MockTransport(armory))
    registry = tmp_path / "config_agents.json"  # tests add agents by rewriting it
    registry.write_text(json.dumps({"agents": AGENTS}), encoding="utf-8")
    settings = Settings(data_dir=tmp_path / "data", agents_registry_path=registry)
    app = create_app(auth_helpers.stack["stronghold"], settings,
                     store=db_gateway, platform=platform, armory=upstream, agent_gateway=agent,
                     legion=httpx.AsyncClient(transport=httpx.MockTransport(legion)), **tool_options(settings, tools))
    with TestClient(app, headers=identity(**IDENTITY)) as test_client:
        mock_tool_catalog(app, monkeypatch)
        test_client.auth = service_auth()
        yield test_client


@pytest.fixture
def make_client(tmp_path, db_gateway, armory, platform, agent, tools, legion):
    from src.api import create_app
    from src.config import Settings
    from src.usage.settings import PricingSettings, UsageSettings

    clients = []

    def make(usage: "UsageSettings | None" = None, pricing: "PricingSettings | None" = None) -> TestClient:
        registry = tmp_path / "config_agents.json"
        registry.write_text(json.dumps({"agents": AGENTS}), encoding="utf-8")
        upstream = httpx.AsyncClient(base_url="http://armory.test", transport=httpx.MockTransport(armory))
        settings = Settings(data_dir=tmp_path / "data", agents_registry_path=registry,
                            usage=usage or UsageSettings(), pricing=pricing or PricingSettings())
        app = create_app(auth_helpers.stack["stronghold"], settings, store=db_gateway, platform=platform, armory=upstream, agent_gateway=agent,
                     legion=httpx.AsyncClient(transport=httpx.MockTransport(legion)), **tool_options(settings, tools, seed_store=False))
        client = TestClient(app, headers=identity(**IDENTITY))
        client.auth = service_auth()
        clients.append(client)
        return client.__enter__()

    yield make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def as_service(client, auth_stack):
    def make(name):
        if name == "portcullis":
            return client
        other = TestClient(client.app)
        other.auth = ServiceAuth(auth_stack[name], "stronghold")
        return other
    return make
