"""The worker's side of the Forge socket: connect out with the pairing token, say hello, keep
alive, hand turn / permission_reply / cancel frames to a TurnRunner, and reconnect when the
connection drops."""

from __future__ import annotations

import asyncio
import json
import logging

from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from src import __version__
from src.config import WorkerConfig
from src.events import TurnRequest
from src.protocol import (
    CancelFrame,
    PermissionReply,
    ReadyFrame,
    heartbeat_frame,
    hello_frame,
    parse_server_frame,
)
from src.providers.base import Provider
from src.runner import CANCEL_GRACE_SECONDS, TurnRunner

logger = logging.getLogger(__name__)

READY_TIMEOUT_SECONDS = 10.0
REJECTED_CLOSE_CODE = 4401


class TokenRejected(Exception):
    """Ember does not accept this pairing token (it was revoked, or is wrong)."""


class WorkerClient:
    def __init__(
        self,
        provider: Provider,
        config: WorkerConfig,
        token: str,
        *,
        connect=ws_connect,
        backoff_start: float = 1.0,
        backoff_max: float = 30.0,
    ) -> None:
        self._provider = provider
        self._config = config
        self._token = token
        self._connect = connect
        self._backoff_start = backoff_start
        self._backoff_max = backoff_max
        self._cancel_grace = CANCEL_GRACE_SECONDS

    async def run(self) -> None:
        """Runs until cancelled, or until Ember rejects the token."""
        delay = self._backoff_start
        while True:
            try:
                reached_ready = await self._session()
                delay = self._backoff_start if reached_ready else delay
            except TokenRejected:
                logger.error(
                    "Ember rejected the %s worker's token. Pair it again with a new token from the Forge page.",
                    self._provider.name,
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("%s worker disconnected: %s", self._provider.name, error)
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._backoff_max)

    async def _session(self) -> bool:
        """One connection. True when it got as far as `ready`."""
        headers = {"Authorization": f"Bearer {self._token}"}
        reached_ready = False
        try:
            async with self._connect(self._config.socket_url, additional_headers=headers) as ws:
                await self._hello(ws)
                reached_ready = True
                await self._serve(ws)
        except InvalidStatus as error:
            if error.response.status_code in (401, 403):
                raise TokenRejected() from error
            raise
        except ConnectionClosed as error:
            if error.rcvd is not None and error.rcvd.code == REJECTED_CLOSE_CODE:
                raise TokenRejected() from error
        return reached_ready

    async def _hello(self, ws) -> None:
        plan = self._config.plan_override.get(self._provider.name) or await self._provider.detect_plan()
        await ws.send(json.dumps(hello_frame(plan, __version__)))
        raw = await asyncio.wait_for(ws.recv(), READY_TIMEOUT_SECONDS)
        if not isinstance(parse_server_frame(raw), ReadyFrame):
            raise ConnectionError("Ember did not answer the hello with ready")
        logger.info("%s worker connected", self._provider.name)

    async def _serve(self, ws) -> None:
        async def send(frame: dict) -> None:
            await ws.send(json.dumps(frame, ensure_ascii=False))

        runner = TurnRunner(self._provider, send, self._cancel_grace)
        beat = asyncio.create_task(self._heartbeat(send))
        try:
            async for raw in ws:
                frame = parse_server_frame(raw)
                if isinstance(frame, TurnRequest):
                    runner.start(frame)
                elif isinstance(frame, PermissionReply):
                    runner.permission_reply(frame.request_id, frame.allow)
                elif isinstance(frame, CancelFrame):
                    await runner.cancel(frame.turn_id)
        finally:
            beat.cancel()
            await asyncio.gather(beat, return_exceptions=True)
            await runner.shutdown()

    async def _heartbeat(self, send) -> None:
        while True:
            await asyncio.sleep(self._config.heartbeat_seconds)
            await send(heartbeat_frame())
