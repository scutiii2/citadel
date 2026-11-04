"""Audio for Bard's text-to-speech results; Bard owns every file."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field

from src.deps import get_log_writer, require_permission
from src.models import Account
from src.services.bard import BardGateway
from src.services.log_service import LogWriter

router = APIRouter(prefix="/api/bard", tags=["bard"])
ID = r"^[0-9a-f]{32}$"


def gateway(request: Request) -> BardGateway:
    return BardGateway(request.app.state.upstream, request.app.state.settings.bard_url, request.app.state.internal_token)


class SpeakIn(BaseModel):
    text: str = Field(min_length=1)
    voice: str | None = Field(default=None, min_length=1, max_length=150)


class SpeakOut(BaseModel):
    file_id: str
    duration_s: float
    voice: str


class VoicesOut(BaseModel):
    voices: list[str]


@router.post("/speak")
async def speak(
    body: SpeakIn,
    account: Account = Depends(require_permission("tools.execute")),
    _transfer: Account = Depends(require_permission("files.download")),
    client: BardGateway = Depends(gateway),
    logs: LogWriter = Depends(get_log_writer),
) -> SpeakOut:
    """Generate one bounded batch and log metadata without the spoken text."""
    result = await client.speak(account, body.text, body.voice)
    await logs.action(account, "bard.speak", f"Generated speech file {result['file_id']}")
    return SpeakOut(**result)


@router.get("/voices")
async def voices(
    account: Account = Depends(require_permission("tools.execute")),
    _transfer: Account = Depends(require_permission("files.download")),
    client: BardGateway = Depends(gateway),
) -> VoicesOut:
    return VoicesOut(**await client.voices(account))


@router.get("/audio/{file_id}")
async def audio(
    request: Request,
    file_id: str = Path(pattern=ID),
    account: Account = Depends(require_permission("tools.execute")),
    _transfer: Account = Depends(require_permission("files.download")),
    client: BardGateway = Depends(gateway),
):
    return await client.stream(file_id, account, range_header=request.headers.get("range"))
