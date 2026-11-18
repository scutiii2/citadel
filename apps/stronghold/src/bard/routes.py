"""/bard: speech from Bard (tools.execute and files.download at Portcullis).

Stronghold asks Bard for the audio and the voice list. Portcullis still streams the finished audio
file to the browser itself. The log never holds the spoken text.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.attachments.services import ToolService
from src.platform import PortcullisClient
from src.requester import Requester, current_requester

router = APIRouter(prefix="/bard", tags=["bard"])


def get_bard(request: Request) -> ToolService:
    return request.app.state.bard


def get_platform(request: Request) -> PortcullisClient:
    return request.app.state.platform


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
async def speak(body: SpeakIn, who: Requester = Depends(current_requester), bard: ToolService = Depends(get_bard),
                platform: PortcullisClient = Depends(get_platform)) -> SpeakOut:
    """One bounded batch of speech."""
    result = await bard.call("POST", "/api/speak", who, {"text": body.text, "voice": body.voice})
    await platform.log_action(who.uid, "bard.speak", f"Generated speech file {result['file_id']}")
    return SpeakOut(**result)


@router.get("/voices")
async def voices(who: Requester = Depends(current_requester), bard: ToolService = Depends(get_bard)) -> VoicesOut:
    """Installed voices only; choosing one belongs to the current run."""
    return VoicesOut(**await bard.call("GET", "/api/voices", who))
