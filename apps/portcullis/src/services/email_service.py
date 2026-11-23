"""Invite and verification templates delivered through MCP's Email capability."""

from __future__ import annotations

from collections.abc import Callable

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Protocol

import httpx
from src.citadel_auth import Keyring, resolved

from src.services.mcp_session import mcp_session
from src.services.traffic import TrafficRecorder


TEMPLATE_DIR = Path(__file__).parent / "email_templates"

_TIMEOUT = httpx.Timeout(30.0, read=60.0)
_MESSAGE_ID = re.compile(r"<[^<>\s@\x00-\x1f\x7f]+@[^<>\s@\x00-\x1f\x7f]+>")


ARMORY_UNREACHABLE = "Armory could not be reached. Check that Armory is running and Portcullis can call it."
EMAIL_DELIVERY_FAILURE = (
    "Email could not be sent. Check MCP Server connectivity, its Email capability and SMTP configuration; "
    "check delivery status before retrying."
)
_READY_MESSAGE = "Email is ready."
_BLOCKED_MESSAGES = frozenset({
    "The Email capability is switched off in Armory.",
    "Email is not set up. Fill in the Email page of Armory Admin.",
    "The email settings are invalid. Check the Email page of Armory Admin.",
    "Armory could not log in to the mail server. Check the Email page of Armory Admin.",
})


def render_template(name: str, **values: str) -> str:
    """Fill ``email_templates/<name>.txt``. ``KeyError`` on a missing value."""
    source = (TEMPLATE_DIR / f"{name}.txt").read_text(encoding="utf-8")
    return Template(source).substitute(values).strip()


class EmailDeliveryError(RuntimeError):
    """Sending failed (SMTP not configured, unreachable, auth rejected, ...)."""


@dataclass(frozen=True)
class EmailHealth:
    ready: bool
    reason: str


class EmailSender(Protocol):
    async def health(self) -> EmailHealth: ...

    async def send_invite(self, to: str, code: str, expires_at: datetime) -> None: ...

    async def send_email_verification(self, to: str, code: str, expires_at: datetime) -> None: ...

    async def send_notification(self, to: str, subject: str, body: str) -> None: ...


class McpEmailSender:
    """Use the shared MCP SMTP service; Ember owns templates, never credentials."""

    def __init__(self, url: str | Callable[[], str], identity: Keyring | None, traffic: TrafficRecorder | None = None) -> None:
        self._url = url
        self._identity = identity
        self._traffic = traffic or TrafficRecorder()

    async def health(self) -> EmailHealth:
        """Probe SMTP without sending mail. Expose only known readiness messages."""
        try:
            with self._traffic.timed("mcp_server", "email.health"):
                async with mcp_session(resolved(self._url), {}, _TIMEOUT) as session:
                    result = await session.call_tool("tool_email_checkHealth", {})
                if getattr(result, "isError", None) is not False:
                    raise ValueError("Email health tool failed")
                data = result.structuredContent
                if not isinstance(data, dict):
                    raise ValueError("Invalid email health result")
                ready, message = data.get("ready"), data.get("message")
                if ready is True and message == _READY_MESSAGE:
                    return EmailHealth(True, _READY_MESSAGE)
                if ready is False and isinstance(message, str) and message in _BLOCKED_MESSAGES:
                    return EmailHealth(False, message)
                raise ValueError("Invalid email health result")
        except Exception:
            return EmailHealth(False, ARMORY_UNREACHABLE)

    async def send_invite(self, to: str, code: str, expires_at: datetime) -> None:
        await self._send(
            to,
            "Your Ember invite code",
            render_template("invite", code=code, email=to, expires_at=f"{expires_at:%Y-%m-%d %H:%M}"),
        )

    async def send_email_verification(self, to: str, code: str, expires_at: datetime) -> None:
        await self._send(
            to,
            "Verify your Ember email",
            render_template("email_verification", code=code, expires_at=f"{expires_at:%Y-%m-%d %H:%M}"),
        )

    async def send_notification(self, to: str, subject: str, body: str) -> None:
        await self._send(to, subject, body)

    async def _send(self, to: str, subject: str, body: str) -> None:
        headers = {}
        # Account emails can precede login/verification; service identity is intentional.
        with self._traffic.timed("mcp_server", "email.send"):
            try:
                async with mcp_session(resolved(self._url), headers, _TIMEOUT) as session:
                    result = await session.call_tool("tool_email_sendEmail", {
                        "to": to, "subject": subject, "body_text": body,
                        "capability_alias": "ember", "prefix_subject": False,
                    })
                if getattr(result, "isError", None) is not False:
                    raise ValueError("Email tool failed")
                data = result.structuredContent
                if data is None:
                    data = json.loads("\n".join(getattr(block, "text", "") for block in result.content))
                message_id = data.get("message_id") if isinstance(data, dict) else None
                if not isinstance(message_id, str) or not _MESSAGE_ID.fullmatch(message_id):
                    raise ValueError("Invalid email tool result")
            except Exception:
                # Upstream exceptions and tool content may contain verification codes.
                # CancelledError propagates unchanged; no automatic retries.
                raise EmailDeliveryError(EMAIL_DELIVERY_FAILURE) from None
