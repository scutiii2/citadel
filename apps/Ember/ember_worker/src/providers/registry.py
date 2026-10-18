"""Builds the real provider for a name. Imports stay inside the branches so a computer
with only one CLI never loads the other's dependencies."""

from __future__ import annotations

from src.providers.base import Provider, SubprocessRunner


def build_provider(name: str) -> Provider:
    if name == "claude":
        from src.providers.claude import ClaudeProvider
        from src.providers.claude_sdk import SdkSessionFactory

        return ClaudeProvider(SdkSessionFactory(), SubprocessRunner())
    if name == "codex":
        from src.providers.codex import CodexProvider
        from src.providers.codex_process import SubprocessCodexSpawner

        return CodexProvider(SubprocessCodexSpawner(), SubprocessRunner())
    raise ValueError(f"Unknown provider: {name}")
