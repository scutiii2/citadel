from dataclasses import replace
from pathlib import Path
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from src.app import create_app
from src.auth import requester
from src.web import UiMount
from tests.test_redeem_route import FakeIdentity
from tests.conftest import signed_in


@pytest.fixture
def dist(tmp_path):
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text("<html>game shell</html>")
    (folder / "assets" / "game.js").write_text("console.log('ready')")
    return folder


def ui_app(dist, config):
    app = create_app(config=config, identity=FakeIdentity(owner=None))
    @app.get("/ascension/profile")
    def profile(owner: str = Depends(requester)):
        return {"owner": owner}
    UiMount(dist, config.ember_origin).mount(app)
    return app


def assert_ui_headers(response, origin):
    assert response.headers["content-security-policy"] == f"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors {origin}"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "x-frame-options" not in response.headers


def test_manifest_index_assets_and_spa_fallback_are_open(dist, config):
    config = replace(config, ember_origin="https://ember.example")
    with TestClient(ui_app(dist, config)) as client:
        manifest = client.get("/manifest.json")
        assert manifest.status_code == 200 and manifest.json()["id"] == "ascension"
        assert manifest.json()["name"] == "Ascension"
        for url in ("/", "/collection", "/collection/guardian"):
            response = client.get(url)
            assert response.status_code == 200 and "game shell" in response.text
            assert_ui_headers(response, config.ember_origin)
        asset = client.get("/assets/game.js")
        assert asset.status_code == 200 and "console.log" in asset.text
        assert_ui_headers(asset, config.ember_origin)
        assert_ui_headers(manifest, config.ember_origin)


def test_spa_never_swallows_api_paths(dist, config):
    app = ui_app(dist, config)
    with TestClient(app) as client:
        assert client.get("/ascension/profile").status_code == 401
        assert client.get("/ascension/profile", headers=signed_in(app, "42")).json() == {"owner": "42"}
        assert client.get("/health").json() == {"status": "ok"}
        for path in ("/ascension", "/ascension/missing", "/session", "/session/missing", "/health/missing"):
            response = client.get(path)
            assert response.status_code == 404 and "game shell" not in response.text


@pytest.mark.parametrize("path", ["/assets/../config.py", "/assets/%2e%2e/config.py", "/assets/%2e%2e/%2e%2e/outside.txt", "/assets/..%5C..%5Coutside.txt", "/assets/missing.js", "/missing.js", "/.env", "/assets/"])
def test_traversal_and_missing_files_are_404(dist, config, path):
    (dist.parent / "outside.txt").write_text("outside the build")
    (dist / "config.py").write_text("not an asset")
    with TestClient(ui_app(dist, config)) as client:
        response = client.get(path)
        assert response.status_code == 404
        assert "outside the build" not in response.text and "not an asset" not in response.text
        assert_ui_headers(response, config.ember_origin)


def test_missing_dist_is_503_while_manifest_and_api_work(tmp_path, config):
    with TestClient(ui_app(tmp_path / "absent", config)) as client:
        response = client.get("/")
        assert response.status_code == 503 and response.text == "UI not built: run npm --prefix web run build"
        assert_ui_headers(response, config.ember_origin)
        assert client.get("/manifest.json").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/ascension/profile").status_code == 401


def test_resolved_asset_symlink_cannot_escape_dist(dist, config):
    outside = dist.parent / "outside.js"
    outside.write_text("outside")
    try:
        (dist / "assets" / "link.js").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or elevated rights")
    with TestClient(ui_app(dist, config)) as client:
        assert client.get("/assets/link.js").status_code == 404


def test_launcher_builds_ui_before_starting_backend():
    launcher = (Path(__file__).resolve().parents[1] / "run.bat").read_text()
    assert 'if not exist "web\\dist\\index.html"' in launcher
    assert 'npm --prefix web ci' in launcher and 'npm --prefix web run build' in launcher
    assert launcher.index('npm --prefix web run build') < launcher.index('python -m src.run')


def test_the_ascended_path_is_never_turned_into_a_page(dist, config):
    client = TestClient(ui_app(dist, config))
    for path in ("/ascended/guardian", "/ascended/guardian/sprite_battle.webp"):
        response = client.get(path)
        assert response.status_code == 404
        assert "game shell" not in response.text
