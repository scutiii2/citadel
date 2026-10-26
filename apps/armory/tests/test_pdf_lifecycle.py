"""Refresh/enable/help/reload exercise against the real capability loader."""
import asyncio
import importlib
import json
from dataclasses import replace

import pytest
from mcp.server.fastmcp import FastMCP

from src import capability_help, commands
from src.config import settings
from src.services import capability_meta, capability_registry
from src.capabilities.pdf_merger.utils import pdf_runtime
from src.services.capability_loader import CapabilityLoader


def test_pdf_refresh_help_and_runtime_survive_reload(tmp_path, monkeypatch):
    import src.server
    server = FastMCP("pdf-lifecycle")
    monkeypatch.setattr(src.server, "mcp", server)
    monkeypatch.setattr(capability_meta, "_BY_FOLDER", {})
    monkeypatch.setattr(capability_registry, "_REGISTRY", {})
    monkeypatch.setattr(commands, "_COMMANDS", {})
    config = tmp_path / "capabilities.json"
    config.write_text("{}")
    loader = CapabilityLoader(server, "src.capabilities", config)

    async def run():
        await loader.refresh()
        assert loader.record_for("pdf").load_error is None
        await loader.set_online("pdf", True)
        assert loader.record_for("pdf").load_error is None
        tools = {t.name: t for t in await server.list_tools()}
        assert {"tool_pdf_inspect", "tool_pdf_listFiles", "tool_pdf_merge"} <= tools.keys()
        assert tools["tool_pdf_merge"].annotations.readOnlyHint is False
        tool_module = importlib.import_module("src.capabilities.pdf_merger.tool")
        from src.capabilities.pdf_merger.utils.pdf_errors import ErrorCode, MergerError
        from mcp.server.fastmcp.exceptions import ToolError
        def fail_merge(_):
            raise MergerError(ErrorCode.INVALID_RANGE, "Bad range")
        with monkeypatch.context() as patch:
            patch.setattr(tool_module.domain.desk, "merge", fail_merge)
            with pytest.raises(ToolError, match="invalid_range: Bad range"):
                await tool_module.tool_pdf_merge(tool_module.MergePlan.model_validate({"segments": [{"file_id": "x"}]}))
        help_body = capability_help.build_help("pdf")
        assert {row["slash_command"] for row in help_body["commands"]} == {"/pdf inspect", "/pdf list_files"}
        old_errors = importlib.import_module("src.capabilities.pdf_merger.utils.errors")
        from src.capabilities.pdf_merger.utils.config import Settings
        runtime = pdf_runtime.Runtime(Settings(store_dir=tmp_path / "store", signing_key=b"x" * 32))
        try:
            await loader.set_online("pdf", False)
            await loader.set_online("pdf", True)
            new_errors = importlib.import_module("src.capabilities.pdf_merger.utils.errors")
            assert new_errors.MergerError is old_errors.MergerError
            async def invalid_download():
                return runtime.service.file_for_download("bad", 0, "bad")
            with pytest.raises(new_errors.MergerError):
                runtime.call(invalid_download())
            from starlette.applications import Starlette
            from starlette.testclient import TestClient
            from src.command_routes import install_command_routes
            from src.upload_routes import install_upload_routes
            from src.services.identity_context import IdentityContextMiddleware
            current_domain = importlib.import_module("src.capabilities.pdf_merger.domain")
            import src.upload_routes
            test_settings = replace(settings, internal_api_token="test", host="127.0.0.1")
            monkeypatch.setattr(current_domain, "get_runtime", lambda _: runtime)
            monkeypatch.setattr(current_domain, "settings", test_settings)
            monkeypatch.setattr(src.upload_routes, "settings", test_settings)
            app = Starlette()
            app.add_middleware(IdentityContextMiddleware)
            install_command_routes(app)
            install_upload_routes(app)
            with TestClient(app) as client:
                assert client.get("/pdf/files/bad/download?exp=0&sig=bad").status_code == 404
                response = client.post("/upload/pdf", headers={"X-Internal-Token": "test", "X-Requester-Uid": "a"}, files={"file": ("bad.pdf", b"bad")})
                assert response.status_code == 400
        finally:
            runtime.close()
    asyncio.run(run())


@pytest.mark.parametrize("updates", [
    {"mcp_wait_seconds": 121}, {"mcp_wait_seconds": float("nan")},
    {"file_ttl_hours": 0}, {"download_link_minutes": -1},
    {"limits": {"max_concurrent_merges": 0}},
    {"limits": {"job_timeout_seconds": float("inf")}},
])
def test_runtime_rejects_unsafe_tuning(tmp_path, updates):
    config = tmp_path / "tuning.json"
    config.write_text(json.dumps(updates))
    test_settings = replace(settings, pdf_merger_config_path=config)
    with pytest.raises(ValueError):
        pdf_runtime._engine_config(test_settings)
