"""Lets the user pick a folder on this computer. The dialog runs in a short-lived child
process, so the event loop never waits on it and a crashed dialog cannot take the worker down."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Protocol

DIALOG_TIMEOUT_SECONDS = 170.0

# Run with `python -c <script> <start folder>`; prints the chosen folder, or nothing when cancelled.
DIALOG_SCRIPT = """
import sys
import tkinter
from tkinter import filedialog

root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)
start = sys.argv[1] if len(sys.argv) > 1 else ""
path = filedialog.askdirectory(
    parent=root, title="Choose a folder for the worker", initialdir=start or None, mustexist=True
)
root.destroy()
sys.stdout.write(path or "")
"""


class FolderPicker(Protocol):
    async def pick(self, start: str | None) -> str | None:
        """The folder the user chose, or None when they cancelled or no dialog could open."""


class SubprocessFolderPicker:
    def __init__(self, script: str = DIALOG_SCRIPT, timeout_seconds: float = DIALOG_TIMEOUT_SECONDS) -> None:
        self._script = script
        self._timeout = timeout_seconds

    async def pick(self, start: str | None) -> str | None:
        folder = start if start and os.path.isdir(start) else ""
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-c", self._script, folder,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            return None
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), self._timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            process.kill()
            await process.wait()
            raise
        if process.returncode != 0:
            return None
        chosen = stdout.decode("utf-8", errors="replace").strip()
        return chosen or None
