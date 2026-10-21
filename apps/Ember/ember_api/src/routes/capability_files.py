"""Authenticated native PDF/video workspaces; Armory owns every file and job."""
from __future__ import annotations

import base64
import binascii
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field

from src.deps import get_db_gateway, get_log_writer, require_permission
from src.models import Account
from src.routes.attachments import AttachmentIn
from src.routes.server_info import get_server_info, _call
from src.services.account_capability_service import AccountCapabilityService
from src.services.capability_files import Area, CapabilityFilesGateway, PUBLIC
from src.services.db_gateway import DbGatewayError, DocumentStore
from src.services.log_service import LogWriter
from src.services.mcp_server_info import McpServerInfo
from src.services.text_extraction import MAX_FILE_BYTES

router = APIRouter(tags=["capability-files"])
ID = r"^[A-Za-z0-9_-]{1,100}$"


class Segment(BaseModel):
    file_id: str = Field(min_length=1, max_length=100, pattern=ID)
    pages: str | None = Field(default=None, max_length=10000)
    rotate: Literal[0, 90, 180, 270] = 0
    fit: Literal["fit", "fill", "original"] | None = None


class OutputOptions(BaseModel):
    filename: str = Field(default="merged.pdf", min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=1000)
    author: str | None = Field(default=None, max_length=1000)
    bookmarks: bool = True
    image_page_size: Literal["A4", "Letter", "match"] = "A4"
    image_fit: Literal["fit", "fill", "original"] = "fit"
    image_margin_mm: float = Field(default=10, ge=0, le=50)


class MergePlan(BaseModel):
    segments: list[Segment] = Field(min_length=1, max_length=50)
    output: OutputOptions = Field(default_factory=OutputOptions)


class ProbeIn(BaseModel):
    url: str = Field(min_length=1, max_length=8192)


class DownloadIn(ProbeIn):
    preset: str = Field(default="best", min_length=1, max_length=64)


class PackageIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)


def gateway(request: Request) -> CapabilityFilesGateway:
    return CapabilityFilesGateway(request.app.state.upstream, request.app.state.settings.mcp_server_url,
                                  request.app.state.internal_token)


def install(area: Area) -> None:
    routes = APIRouter(prefix=f"/api/{PUBLIC[area]}")

    async def access(account: Account = Depends(require_permission("tools.execute")),
                     store: DocumentStore = Depends(get_db_gateway)) -> Account:
        try:
            added = await AccountCapabilityService(store, account.uid).get()
        except DbGatewayError as error:
            raise HTTPException(503, "Account capabilities storage is unavailable") from error
        if area not in added.capabilities:
            raise HTTPException(403, "Add this capability from the Supermarket first.")
        return account

    @routes.get("/files")
    async def files(account: Account = Depends(access), client: CapabilityFilesGateway = Depends(gateway)):
        return client.local_links(area, await client.request(area, "GET", "/files", account))

    @routes.delete("/files/{file_id}", status_code=204)
    async def remove(file_id: str = Path(pattern=ID), account: Account = Depends(access),
                     client: CapabilityFilesGateway = Depends(gateway), logs: LogWriter = Depends(get_log_writer)):
        await client.request(area, "DELETE", f"/files/{file_id}", account)
        await logs.action(account, f"{area}.file_delete", f"Deleted file {file_id}")

    @routes.get("/files/{file_id}/download")
    async def download(request: Request, file_id: str = Path(pattern=ID), account: Account = Depends(access),
                       _transfer: Account = Depends(require_permission("files.download")),
                       client: CapabilityFilesGateway = Depends(gateway)):
        return await client.stream(area, file_id, account, range_header=request.headers.get("range"))

    @routes.get("/jobs/{job_id}")
    async def job(job_id: str = Path(pattern=ID), account: Account = Depends(access),
                  client: CapabilityFilesGateway = Depends(gateway)):
        return client.local_links(area, await client.request(area, "GET", f"/jobs/{job_id}", account))

    @routes.post("/jobs/{job_id}/cancel")
    async def cancel(job_id: str = Path(pattern=ID), account: Account = Depends(access),
                     client: CapabilityFilesGateway = Depends(gateway), logs: LogWriter = Depends(get_log_writer)):
        result = await client.request(area, "POST", f"/jobs/{job_id}/cancel", account, json={})
        await logs.action(account, f"{area}.job_cancel", f"Cancelled job {job_id}")
        return result

    if area == "pdf":
        @routes.post("/files")
        async def upload(body: AttachmentIn, account: Account = Depends(access),
                         _transfer: Account = Depends(require_permission("files.upload")),
                         info: McpServerInfo = Depends(get_server_info), logs: LogWriter = Depends(get_log_writer)):
            filename = body.filename.replace("\\", "/").rsplit("/", 1)[-1]
            if not filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif", ".heic")):
                raise HTTPException(400, "Upload a PDF or supported image")
            try:
                content = base64.b64decode(body.data, validate=True)
            except (binascii.Error, ValueError) as error:
                raise HTTPException(400, "data must be base64") from error
            if len(content) > MAX_FILE_BYTES:
                raise HTTPException(413, "The file is larger than 15 MB")
            result = await _call(info.upload_pdf(account, filename, content))
            await logs.action(account, "pdf.upload", f"Uploaded file {result['file_id']}")
            return result

        @routes.get("/files/{file_id}/content")
        async def content(request: Request, file_id: str = Path(pattern=ID), account: Account = Depends(access),
                          _transfer: Account = Depends(require_permission("files.download")),
                          client: CapabilityFilesGateway = Depends(gateway)):
            return await client.stream("pdf", file_id, account, content=True, range_header=request.headers.get("range"))

        @routes.post("/merge")
        async def merge(body: MergePlan, account: Account = Depends(access),
                        client: CapabilityFilesGateway = Depends(gateway), logs: LogWriter = Depends(get_log_writer)):
            result = await client.request("pdf", "POST", "/merge", account, json=body.model_dump())
            await logs.action(account, "pdf.merge", f"Started merge job {result['job_id']}")
            return result
    else:
        @routes.get('/packages')
        async def packages(account: Account = Depends(access), client: CapabilityFilesGateway = Depends(gateway)):
            return client.local_links('video', await client.request('video', 'GET', '/packages', account))

        @routes.post('/packages')
        async def create_package(body: PackageIn, account: Account = Depends(access),
                                 client: CapabilityFilesGateway = Depends(gateway)):
            return await client.request('video', 'POST', '/packages', account, json=body.model_dump())

        @routes.get('/packages/{package_id}')
        async def package(package_id: str = Path(pattern=ID), account: Account = Depends(access),
                          client: CapabilityFilesGateway = Depends(gateway)):
            return client.local_links('video', await client.request('video', 'GET', f'/packages/{package_id}', account))

        @routes.post('/packages/{package_id}/items')
        async def add_media(body: DownloadIn, package_id: str = Path(pattern=ID), account: Account = Depends(access),
                            client: CapabilityFilesGateway = Depends(gateway)):
            return await client.request('video', 'POST', f'/packages/{package_id}/items', account, json=body.model_dump())

        @routes.delete('/packages/{package_id}', status_code=204)
        async def delete_package(package_id: str = Path(pattern=ID), account: Account = Depends(access),
                                 client: CapabilityFilesGateway = Depends(gateway), logs: LogWriter = Depends(get_log_writer)):
            await client.request('video', 'DELETE', f'/packages/{package_id}', account)
            await logs.action(account, 'video.package_delete', f'Removed package {package_id}')

        @routes.delete('/packages/{package_id}/items/{item_id}')
        async def remove_media(package_id: str = Path(pattern=ID), item_id: str = Path(pattern=ID),
                               account: Account = Depends(access), client: CapabilityFilesGateway = Depends(gateway)):
            return await client.request('video', 'DELETE', f'/packages/{package_id}/items/{item_id}', account)

        @routes.post('/packages/{package_id}/start')
        async def start_package(package_id: str = Path(pattern=ID), account: Account = Depends(access),
                                client: CapabilityFilesGateway = Depends(gateway), logs: LogWriter = Depends(get_log_writer)):
            result = await client.request('video', 'POST', f'/packages/{package_id}/start', account, json={})
            await logs.action(account, 'video.package_start', f'Started package {package_id} as job {result["job_id"]}')
            return result

        @routes.post("/probe")
        async def probe(body: ProbeIn, account: Account = Depends(access),
                        client: CapabilityFilesGateway = Depends(gateway)):
            return await client.request("video", "POST", "/probe", account, json=body.model_dump())

        @routes.post("/downloads")
        async def start(body: DownloadIn, account: Account = Depends(access),
                        client: CapabilityFilesGateway = Depends(gateway), logs: LogWriter = Depends(get_log_writer)):
            result = await client.request("video", "POST", "/downloads", account, json=body.model_dump())
            await logs.action(account, "video.download", f"Started download job {result['job_id']}")
            return result

    router.include_router(routes)


install("pdf")
install("video")
