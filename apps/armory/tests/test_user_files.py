"""The shared store: what it keeps, whose it is, and what a link opens."""
import io
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from src.services.file_errors import ErrorCode, FileError
from src.services.user_files.kinds import PAGED
from src.services.user_files.runtime import FilesRuntime, validate_tuning
from src.services.user_files.service import Settings, chunks_of


def png(width=10, height=10):
    stream = io.BytesIO()
    Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def runtime(tmp_path):
    runtime = FilesRuntime(Settings(store_dir=tmp_path / "store", signing_key=b"x" * 32,
                                    public_base_url="http://testserver"))
    try:
        yield runtime
    finally:
        runtime.close()


def keep(runtime, owner, name, content, **options):
    return runtime.call(runtime.files.upload(owner, name, chunks_of(content), **options))


@pytest.mark.parametrize("name,content,kind,pages", [
    ("notes.md", b"# hi", "text", 0), ("report.docx", b"PK\x03\x04", "document", 0),
    ("sales.csv", b"a,b\n1,2", "table", 0), ("voice.mp3", b"ID3", "audio", 0),
    ("photo.bin", png(), "image", 1),
])
def test_each_accepted_type_gets_its_kind(runtime, name, content, kind, pages):
    stored = keep(runtime, "a", name, content)
    assert (stored.kind, stored.pages) == (kind, pages)


def test_unknown_types_and_wrong_kinds_are_refused(runtime):
    for name, options in (("run.exe", {}), ("notes.txt", {"kinds": PAGED})):
        with pytest.raises(FileError) as refused:
            keep(runtime, "a", name, b"MZ\x00\x00", **options)
        assert refused.value.code == ErrorCode.UNSUPPORTED_TYPE
    assert runtime.files.list("a") == []


def test_another_account_sees_nothing_and_kinds_filter(runtime):
    text = keep(runtime, "a", "n.txt", b"hello")
    image = keep(runtime, "a", "p.png", png())
    files = runtime.files
    assert [f.file_id for f in files.list("a", PAGED)] == [image.file_id]
    assert files.list("b") == []
    for file_id, owner, kinds in ((text.file_id, "b", None), (text.file_id, "a", PAGED)):
        with pytest.raises(FileError) as hidden:
            files.get(file_id, owner, kinds)
        assert hidden.value.code == ErrorCode.FILE_NOT_FOUND
    found, failed = files.lookup("a", [image.file_id, "f_" + "0" * 32])
    assert [f.file_id for f in found] == [image.file_id] and len(failed) == 1


def test_view_downscales_images_only(runtime):
    wide = keep(runtime, "a", "wide.png", png(3000, 100))
    data, media_type = runtime.files.view(wide)
    with Image.open(io.BytesIO(data)) as shown:
        assert media_type == "image/png" and shown.width == 1568 and shown.getpixel((0, 0)) == (255, 255, 255)
    with pytest.raises(FileError, match="not an image"):
        runtime.files.view(keep(runtime, "a", "n.txt", b"x"))


def test_links_are_signed(runtime):
    stored = keep(runtime, "a", "n.txt", b"hello")
    url = urlsplit(runtime.files.download_url(stored))
    query = parse_qs(url.query)
    assert url.path == f"/files/{stored.file_id}/download"
    assert runtime.files.file_for_download(stored.file_id, int(query["exp"][0]), query["sig"][0]) == stored
    with pytest.raises(FileError):
        runtime.files.file_for_download(stored.file_id, int(query["exp"][0]), "forged")


def test_tuning_is_checked():
    assert validate_tuning({})["max_upload_bytes"] == 15 * 1024 * 1024
    for bad in ({"file_ttl_hours": 0}, {"limits": {"max_file_mb": 0}}):
        with pytest.raises(ValueError):
            validate_tuning(bad)
