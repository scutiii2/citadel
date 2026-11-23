"""Limits and answer cache of the decision gateway."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    max_chars: int = 16000
    max_inflight: int = 8
    cache_enabled: bool = True
    cache_seconds: int = 300
    cache_entries: int = 500
