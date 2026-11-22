import asyncio

import httpx

from citadel_auth.ready import Dependency, Probe


def transport(handler):
    return httpx.MockTransport(handler)


async def run(deps, handler, ttl=0.0):
    probe = Probe("legion", client_factory=lambda: httpx.AsyncClient(transport=transport(handler)), ttl=ttl)
    return await probe.check(deps)


def test_states_for_up_down_slow_rejected_and_missing():
    def handler(request):
        host = request.url.host
        if host == "up":
            return httpx.Response(200, json={"status": "ok"})
        if host == "rejected":
            return httpx.Response(401)
        if host == "broken":
            return httpx.Response(500)
        if host == "slow":
            raise httpx.ReadTimeout("slow", request=request)
        raise httpx.ConnectError("down", request=request)

    deps = [
        Dependency("up", lambda: "http://up:1"),
        Dependency("down", lambda: "http://down:1"),
        Dependency("slow", lambda: "http://slow:1"),
        Dependency("rejected", lambda: "http://rejected:1"),
        Dependency("broken", lambda: "http://broken:1"),
        Dependency("missing", lambda: None),
    ]
    report = asyncio.run(run(deps, handler))
    states = {d["name"]: (d["state"], d["last_error"]) for d in report["dependencies"]}
    assert report["service"] == "legion" and report["status"] == "up"
    assert states == {
        "up": ("reachable", None),
        "down": ("unreachable", "unavailable"),
        "slow": ("unreachable", "timeout"),
        "rejected": ("unreachable", "rejected"),
        "broken": ("unreachable", "error"),
        "missing": ("not_configured", None),
    }


def test_the_report_is_cached_for_the_ttl():
    calls = []

    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(200)

    async def go():
        probe = Probe("x", client_factory=lambda: httpx.AsyncClient(transport=transport(handler)), ttl=60.0)
        deps = [Dependency("up", lambda: "http://up:1")]
        await probe.check(deps)
        await probe.check(deps)

    asyncio.run(go())
    assert calls == ["up"]


def test_no_address_text_leaks_an_exception():
    def handler(request):
        raise httpx.ConnectError("secret-host.internal refused", request=request)

    report = asyncio.run(run([Dependency("a", lambda: "http://a:1")], handler))
    assert "secret" not in str(report)


def test_address_resolvers_can_be_async_and_fail_without_disclosing_input():
    async def address():
        return "http://user:secret@demo.invalid"

    async def failed():
        raise RuntimeError("private host")

    def unexpected_request(request):
        raise AssertionError("invalid or unavailable addresses should not be probed")

    report = asyncio.run(run([Dependency("invalid", address), Dependency("missing", failed)], unexpected_request))
    assert all(row["state"] == "not_configured" and row["address"] is None for row in report["dependencies"])
