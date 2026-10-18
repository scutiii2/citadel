"""The real process behind CodexProvider: `codex exec` as an asyncio subprocess."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from src.providers.codex import CodexProcess


class _SubprocessCodexProcess:
    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        # stderr is read as it arrives, so a chatty CLI can never block on a full pipe.
        self._stderr = asyncio.create_task(process.stderr.read())

    async def lines(self) -> AsyncIterator[str]:
        async for raw in self._process.stdout:
            yield raw.decode("utf-8", errors="replace").rstrip("\r\n")

    async def wait(self) -> int:
        return await self._process.wait()

    async def stderr_text(self) -> str:
        try:
            return (await self._stderr).decode("utf-8", errors="replace")
        except Exception:
            return ""

    def terminate(self) -> None:
        if self._process.returncode is None:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass


class SubprocessCodexSpawner:
    async def spawn(self, args: list[str], cwd: str, stdin_text: str) -> CodexProcess:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        process.stdin.write(stdin_text.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()
        return _SubprocessCodexProcess(process)
