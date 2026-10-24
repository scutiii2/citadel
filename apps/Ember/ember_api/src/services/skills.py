"""Account-scoped access to mcp_server's learned skills, never a browser-selected owner.

Skills are how-tos the assistant proposed and the user approves. mcp_server owns them; this is a
thin client that sends the internal token and the signed-in account's uid. Logs carry no skill text.
"""
from __future__ import annotations

import logging
from typing import Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from src.services.mcp_server_info import base_url

logger = logging.getLogger(__name__)

SkillStatus = Literal["proposed", "active", "retired"]


class Skill(BaseModel):
    id: int = Field(gt=0)
    title: str
    when_to_use: str
    steps: str
    tools: str
    status: SkillStatus
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    created_at: str


class SkillsError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(message)


_MESSAGES = {
    404: "Skills is not enabled or this skill no longer exists",
    409: "You already have the maximum number of active skills. Retire one first.",
    422: "That is not a valid skill status",
}


class SkillsClient:
    def __init__(self, client: httpx.AsyncClient, mcp_url: str, token: str | None) -> None:
        self._client = client
        self._base = base_url(mcp_url)
        self._headers = {"X-Internal-Token": token} if token else {}

    def _owner(self, uid: str) -> str:
        return f"{self._base}/skills/owners/{quote(uid, safe='')}"

    async def _send(self, method: str, url: str, body: dict | None = None) -> httpx.Response:
        try:
            response = await self._client.request(method, url, headers=self._headers, json=body,
                                                  timeout=httpx.Timeout(10), follow_redirects=False)
        except httpx.HTTPError as error:
            raise SkillsError(503, "Skill storage is unavailable") from error
        if response.status_code in _MESSAGES:
            raise SkillsError(response.status_code, _MESSAGES[response.status_code])
        if not response.is_success:
            raise SkillsError(503, "Skill storage is unavailable")
        return response

    @staticmethod
    def _parse(response: httpx.Response, kind):
        try:
            return TypeAdapter(kind).validate_python(response.json())
        except (ValueError, ValidationError) as error:
            raise SkillsError(503, "Skill storage returned an invalid response") from error

    async def list(self, uid: str) -> list[Skill]:
        return self._parse(await self._send("GET", f"{self._owner(uid)}/skills"), list[Skill])

    async def set_status(self, uid: str, skill_id: int, status: SkillStatus) -> Skill:
        response = await self._send("PUT", f"{self._owner(uid)}/skills/{skill_id}/status", {"status": status})
        return self._parse(response, Skill)

    async def delete(self, uid: str, skill_id: int) -> None:
        await self._send("DELETE", f"{self._owner(uid)}/skills/{skill_id}")

    async def purge(self, uid: str) -> bool:
        """DELETE /skills/owners/<uid> on mcp_server. True only when it confirmed; never raises."""
        if not uid:
            return False
        try:
            await self._send("DELETE", self._owner(uid))
        except SkillsError as error:
            logger.warning("skills purge failed (status %s)", error.status)
            return False
        except Exception as error:  # noqa: BLE001 - best effort must not undo an account deletion
            logger.warning("skills purge failed (%s)", type(error).__name__)
            return False
        return True
