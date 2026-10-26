"""Fixed, authenticated HTTP adapters for Ember's native media screens.
The internal token authenticates the gateway; the UID scopes every operation."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging

from pydantic import ValidationError
from starlette.responses import FileResponse, JSONResponse

from src.config import settings
from src.services import capability_registry
from src.services.identity_context import REQUESTER_UID_HEADER
from src.services.internal_token import is_exposed_without_token

logger = logging.getLogger(__name__)


async def media_ui(request):
    kind = request.url.path.split("/")[1]
    expected = settings.internal_api_token
    if not expected or not hmac.compare_digest(expected, request.headers.get("X-Internal-Token", "")):
        return JSONResponse({"error": "Invalid or missing internal API token"}, status_code=401)
    uid = request.headers.get(REQUESTER_UID_HEADER, "").strip()
    if not uid:
        return JSONResponse({"error": "The requesting account is not identified"}, status_code=400)
    try:
        enabled = capability_registry.is_enabled(kind)
    except KeyError:
        enabled = False
    if not enabled or is_exposed_without_token(settings.host, expected):
        return JSONResponse({"error": "Capability is unavailable"}, status_code=503)

    ServiceError = ()
    try:
        # Imports stay behind the toggle: an offline optional engine is inert.
        if kind == "pdf":
            from src.capabilities.pdf_merger.utils.pdf_errors import MergerError as ServiceError
        else:
            from src.capabilities.media_downloader.utils.errors import DownloaderError as ServiceError
        body = await request.json() if request.method == "POST" and not request.url.path.endswith("/cancel") else None
        result = await asyncio.to_thread(_pdf_operation if kind == "pdf" else _video_operation, request, uid, body)
        if isinstance(result, FileResponse):
            return result
        return JSONResponse(result)
    except (ValidationError, json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse({"error": {"code": "invalid_request", "message": "Invalid request body"}}, status_code=422)
    except ServiceError as error:
        if str(error.code) in {"file_not_found", "job_not_found", "package_not_found"}:
            noun = {"file_not_found": "File", "job_not_found": "Job", "package_not_found": "Package"}[str(error.code)]
            return JSONResponse({"error": {"code": str(error.code), "message": f"{noun} is not available"}}, status_code=404)
        if str(error.code) == "internal_error":
            logger.exception("Native %s UI operation failed", kind)
            return JSONResponse({"error": "Capability is unavailable"}, status_code=503)
        return JSONResponse(error.to_body(), status_code=error.http_status)
    except Exception:
        logger.exception("Native %s UI operation failed", kind)
        return JSONResponse({"error": "Capability is unavailable"}, status_code=503)


def _pdf_operation(request, uid, body):
    from src.capabilities.pdf_merger.utils.models import FileInfo, MergePlan
    from src.capabilities.pdf_merger.utils.service import Caller
    from src.capabilities.pdf_merger.utils.pdf_runtime import get_runtime

    runtime = get_runtime(settings)
    caller = Caller(uid)
    path = request.url.path
    file_id = request.path_params.get("file_id")
    job_id = request.path_params.get("job_id")

    async def operation():
        service = runtime.service
        if file_id:
            if request.method == "DELETE":
                await service.delete_file(caller, file_id)
                return {"ok": True}
            file = service.get_file(caller, file_id)
            return FileResponse(service.file_path(file), media_type=file.mime, headers={
                "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox", "Referrer-Policy": "no-referrer",
            })
        if job_id:
            job = service.get_job(caller, job_id)
            if path.endswith("/cancel"):
                job.cancel()
                return {"ok": True}
            event = dict(job.events[-1]) if job.events else {"type": "queued"}
            result = None
            if event["type"] == "done":
                result = {k: v for k, v in event.items() if k != "type"}
                # Completed jobs mint links with the same expiry rules as lists.
                result["download_url"] = service.download_url(service.get_file(caller, event["file_id"]))
            return {"job_id": job.id, "state": event["type"], "done": event.get("done", result["pages"] if result else 0),
                    "total": event.get("total", result["pages"] if result else 0), "result": result,
                    "error": {"code": event["code"], "message": event["message"]} if event["type"] == "error" else None}
        if path.endswith("/merge"):
            job = service.start_merge(caller, MergePlan.model_validate(body))
            return {"job_id": job.id}
        return [{**FileInfo.of(file).model_dump(mode="json"), "download_url": service.download_url(file)}
                for file in service.list_files(caller)]

    return runtime.call(operation())


def _video_operation(request, uid, body):
    from src.capabilities.media_downloader.domain import _require_ffmpeg
    from src.capabilities.media_downloader.utils.models import DownloadRequest, ProbeRequest, PackageCreate, PackageAdd
    from src.capabilities.media_downloader.utils.service import Caller
    from src.capabilities.media_downloader.utils.media_downloads import get_runtime

    caller = Caller("uid:" + uid)
    path = request.url.path
    file_id = request.path_params.get("file_id")
    job_id = request.path_params.get("job_id")

    async def operation(service):
        if '/packages' in path:
            package_id = request.path_params.get('package_id')
            item_id = request.path_params.get('item_id')
            if item_id:
                return service.packages.remove(caller, package_id, item_id).model_dump(mode='json')
            if path.endswith('/items'):
                payload = PackageAdd.model_validate(body)
                return (await service.packages.add(caller, package_id, payload.url, payload.preset)).model_dump(mode='json')
            if path.endswith('/start'):
                package = service.packages.get(caller, package_id)
                if any(item.preset != 'photos' for item in package.items):
                    _require_ffmpeg()
                return {'job_id': service.packages.start(caller, package_id).id}
            if package_id:
                if request.method == 'DELETE':
                    service.packages.delete(caller, package_id)
                    return {'ok': True}
                return service.packages.get(caller, package_id).model_dump(mode='json')
            if request.method == 'POST':
                return service.packages.create(caller, PackageCreate.model_validate(body).name).model_dump(mode='json')
            return [package.model_dump(mode='json') for package in service.packages.list(caller)]
        if file_id:
            await service.delete_file(caller, file_id)
            return {"ok": True}
        if job_id:
            if path.endswith("/cancel"):
                service.cancel_job(caller, job_id)
                return {"ok": True}
            return service.job_status(caller, job_id).model_dump(mode="json")
        if path.endswith("/probe"):
            payload = ProbeRequest.model_validate(body)
            result = await service.probe(payload.url)
            if not result.photo_count:
                _require_ffmpeg()
            return result.model_dump(mode="json")
        if path.endswith("/downloads"):
            payload = DownloadRequest.model_validate(body)
            if payload.preset != "photos":
                _require_ffmpeg()
            job = await service.start_download(caller, payload.url, payload.preset)
            return {"job_id": job.id}
        return [service.file_info(file).model_dump(mode="json") for file in service.list_files(caller)]

    return get_runtime().call(operation)


def install_media_ui_routes(app):
    for kind in ("pdf", "media"):
        base = f"/{kind}/ui"
        app.add_route(base + "/files", media_ui, methods=["GET"])
        app.add_route(base + "/files/{file_id}", media_ui, methods=["DELETE"])
        app.add_route(base + "/jobs/{job_id}", media_ui, methods=["GET"])
        app.add_route(base + "/jobs/{job_id}/cancel", media_ui, methods=["POST"])
    app.add_route("/pdf/ui/files/{file_id}/content", media_ui, methods=["GET"])
    app.add_route("/pdf/ui/merge", media_ui, methods=["POST"])
    app.add_route("/media/ui/probe", media_ui, methods=["POST"])
    app.add_route("/media/ui/downloads", media_ui, methods=["POST"])
    app.add_route('/media/ui/packages', media_ui, methods=['GET', 'POST'])
    app.add_route('/media/ui/packages/{package_id}', media_ui, methods=['GET', 'DELETE'])
    app.add_route('/media/ui/packages/{package_id}/items', media_ui, methods=['POST'])
    app.add_route('/media/ui/packages/{package_id}/items/{item_id}', media_ui, methods=['DELETE'])
    app.add_route('/media/ui/packages/{package_id}/start', media_ui, methods=['POST'])
