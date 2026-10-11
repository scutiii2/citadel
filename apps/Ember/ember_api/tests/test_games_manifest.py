import asyncio
import httpx
import pytest
from src.services.game_manifest import ManifestError, ManifestFetcher, normalize_game_url


def good(**changes):
    return {"id": "ascension", "name": "Ascension", "description": "Collect.", "icon": "", "version": "1.0", **changes}


def fetch(handler, **options):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            return await ManifestFetcher(client, allow_private=True, **options).fetch("http://127.0.0.1:8060/base")
    return asyncio.run(go())


def test_valid_manifest_and_request():
    def handler(request):
        assert str(request.url) == "http://127.0.0.1:8060/base/manifest.json"
        assert request.extensions["timeout"]["read"] == 5.0
        return httpx.Response(200, json=good())
    manifest = fetch(handler)
    assert manifest.id == "ascension" and manifest.raw == good()


@pytest.mark.parametrize("payload", [[], {}, good(id="Bad_ID"), good(id="a" * 64), good(id="a\n"), good(name=""), good(name=" " ), good(name="x"*81), good(name=4), good(description="x"*301), good(icon="x"*301), good(version="x"*41), good(icon=None)])
def test_invalid_manifest(payload):
    with pytest.raises(ManifestError):
        fetch(lambda r: httpx.Response(200, json=payload))


def test_non_json():
    with pytest.raises(ManifestError):
        fetch(lambda r: httpx.Response(200, content=b"not json"))


@pytest.mark.parametrize("status", [302, 404, 500])
def test_response_refused_without_redirect(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"location": "http://other/"})
    with pytest.raises(ManifestError):
        fetch(handler)
    assert len(calls) == 1


def test_size_cap():
    with pytest.raises(ManifestError, match="too large"):
        fetch(lambda r: httpx.Response(200, content=b" " * 65537))


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_transport_error_is_safe(error):
    def handler(request):
        raise error("private diagnostic", request=request)
    with pytest.raises(ManifestError, match="^Cannot reach the game$"):
        fetch(handler)


@pytest.mark.parametrize("url", ["ftp://x", "http://u:p@x", "http://", "not a url", "http://x:bad", "http://x:99999", "http://x/\n", "http://x\\@evil", "http://x/" + "a"*1000])
def test_invalid_url(url):
    with pytest.raises(ManifestError):
        normalize_game_url(url, allow_private=True)


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST.", "a.localhost", "127.0.0.1", "10.0.0.5", "192.168.1.2", "169.254.1.1", "[::1]", "[::ffff:127.0.0.1]", "0.0.0.0", "224.0.0.1"])
def test_private_hosts_require_flag(host):
    url = f"http://{host}:8060"
    with pytest.raises(ManifestError):
        normalize_game_url(url, allow_private=False)
    assert normalize_game_url(url, allow_private=True)


def test_public_url_and_subpath_normalization():
    assert normalize_game_url("https://Example.COM/games/a/?x=1#ticket=x", allow_private=False) == "https://example.com/games/a"
    assert normalize_game_url("https://8.8.8.8", allow_private=False) == "https://8.8.8.8"
