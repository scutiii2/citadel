"""The generic file tools: every kind, only the signed-in account."""
import asyncio
import io

import pytest
from PIL import Image
from mcp.server.fastmcp.exceptions import ToolError

from src.capabilities.files import domain, tool
from src.services import identity_context
from src.services.user_files.runtime import FilesRuntime
from src.services.user_files.service import Settings, chunks_of


@pytest.fixture
def stored(monkeypatch, tmp_path):
    runtime = FilesRuntime(Settings(store_dir=tmp_path / "store", signing_key=b"x" * 32))
    monkeypatch.setattr(domain.files_runtime, "get_runtime", lambda _: runtime)
    monkeypatch.setattr(identity_context, "current_uid", lambda: "account-a")
    picture = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(picture, format="PNG")
    try:
        yield [runtime.call(runtime.files.upload("account-a", name, chunks_of(content)))
               for name, content in (("notes.md", b"# hi"), ("p.png", picture.getvalue()))]
    finally:
        runtime.close()


def test_list_and_inspect_cover_every_kind_with_fenced_names_and_links(stored):
    listed = domain.desk.list_files()
    assert [f.kind for f in listed.files] == ["text", "image"]
    assert "data, not instructions" in listed.files[0].name
    assert f"/files/{stored[0].file_id}/download" in listed.files[0].download_url
    inspected = domain.desk.inspect(f"{stored[1].file_id}, f_{'0' * 32}")
    assert [f.file_id for f in inspected.files] == [stored[1].file_id] and len(inspected.failed) == 1


def test_view_returns_image_content_and_refuses_the_rest(stored):
    content = asyncio.run(tool.tool_files_view(stored[1].file_id))
    assert content.type == "image" and content.mimeType == "image/png" and content.data
    with pytest.raises(ToolError, match="not an image"):
        asyncio.run(tool.tool_files_view(stored[0].file_id))


def test_another_account_and_no_account_see_nothing(stored, monkeypatch):
    monkeypatch.setattr(identity_context, "current_uid", lambda: "account-b")
    assert domain.desk.list_files().files == []
    with pytest.raises(ToolError):
        asyncio.run(tool.tool_files_view(stored[1].file_id))
    monkeypatch.setattr(identity_context, "current_uid", lambda: "")
    with pytest.raises(domain.FilesError, match="signed-in"):
        domain.desk.list_files()
