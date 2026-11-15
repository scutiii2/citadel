"""Shared fixtures. Tests never read the real .env, the shared token file, Treasury or Portcullis."""

import json
import os

os.environ["INTERNAL_TOKEN_FILE"] = ""

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

IDENTITY = {
    "X-Requester-Uid": "u-1",
    "X-Requester-Username": "ana",
    "X-Requester-Email": "ana@example.com",
}


class FakeDbGateway:
    """In-memory DocumentStore: same behaviour as Treasury for get/put/delete/query."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict] = {}

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


class FakePlatform:
    """Portcullis as Stronghold sees it: every account is a recipient, every switch is on."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.errors: list[tuple[str, str]] = []
        self.actions: list[tuple[str, str, str]] = []

    async def recipient(self, uid, permission):
        return {"uid": uid, "email": f"{uid}@example.com"}

    async def switches(self):
        return {"calendar_inapp": True, "calendar_email": True, "calendar_push": True}

    async def notify(self, uid, subject, body):
        self.sent.append((uid, subject, body))

    async def log_action(self, uid, action, message):
        self.actions.append((uid, action, message))

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

    async def ask(self, url, caller, **kwargs):
        raise AssertionError("this test did not expect an ask() call")

    async def interpret(self, url, caller, text):
        from src.agents.gateway import AgentCallError

        self.interprets.append(text)
        if self.fail:
            raise AgentCallError(self.fail)
        return {"response": self.summary, "provider_id": "claude", "model": "claude-test", "total_tokens": 10}


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
    """Scribe, Reader and Bard: each answers through its own handler and records its requests."""
    return {name: FakeArmory() for name in ("scribe", "reader", "bard")}


def tool_clients(tools: dict[str, FakeArmory]) -> dict[str, httpx.AsyncClient]:
    return {name: httpx.AsyncClient(base_url=f"http://{name}.test", transport=httpx.MockTransport(fake))
            for name, fake in tools.items()}


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform()


@pytest.fixture
def client(tmp_path, db_gateway, armory, platform, agent, tools, legion):
    """The app with its lifespan running, an open token and the requester headers already set."""
    from src.api import create_app
    from src.config import Settings

    upstream = httpx.AsyncClient(base_url="http://armory.test", transport=httpx.MockTransport(armory))
    registry = tmp_path / "config_agents.json"  # tests add agents by rewriting it
    registry.write_text(json.dumps({"agents": AGENTS}), encoding="utf-8")
    app = create_app("shared-test-token", Settings(data_dir=tmp_path / "data", agents_registry_path=registry),
                     store=db_gateway, platform=platform, armory=upstream, agent_gateway=agent,
                     tools=tool_clients(tools), legion=httpx.AsyncClient(transport=httpx.MockTransport(legion)))
    with TestClient(app, headers={**IDENTITY, "X-Internal-Token": "shared-test-token"}) as test_client:
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
        app = create_app("shared-test-token", settings, store=db_gateway, platform=platform, armory=upstream, agent_gateway=agent,
                     tools=tool_clients(tools), legion=httpx.AsyncClient(transport=httpx.MockTransport(legion)))
        client = TestClient(app, headers={**IDENTITY, "X-Internal-Token": "shared-test-token"})
        clients.append(client)
        return client.__enter__()

    yield make
    for client in clients:
        client.__exit__(None, None, None)
