"""Limits of the chat gateway."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    max_messages: int = 500
    max_text: int = 400000
    max_tools: int = 128
    max_images: int = 20
    max_image_mb: int = 16
    max_audio_mb: int = 20
    max_inflight: int = 16
