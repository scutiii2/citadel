"""Local embedding boundary; the default implementation talks only to configured Ollama."""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from typing import Protocol
from urllib.parse import urlsplit



class Embedder(Protocol):
    identity: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    """Batch embeddings from a user-operated Ollama instance; no remote AI provider."""

    def __init__(self, base_url: str, model: str, timeout: float = 30):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("OBSIDIAN_OLLAMA_URL must be an HTTP(S) base URL without credentials")
        self.url, self.model, self.timeout = base_url.rstrip("/"), model, timeout
        self.identity = f"ollama:{self.url}:{model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        request = urllib.request.Request(
            self.url + "/api/embed",
            data=json.dumps({"model": self.model, "input": texts, "truncate": False}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            # No redirect can forward vault content to another host.
            from src.capabilities.obsidian.utils.gateway import _NoRedirect
            with urllib.request.build_opener(_NoRedirect()).open(request, timeout=self.timeout) as response:
                raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise ValueError("Embedding response too large")
                vectors = json.loads(raw)["embeddings"]
            if len(vectors) != len(texts) or not vectors or not vectors[0]:
                raise ValueError("Invalid embedding batch")
            if any(len(v) != len(vectors[0]) or not all(math.isfinite(x) for x in v) or not any(v) for v in vectors):
                raise ValueError("Invalid embedding vector")
            return vectors
        except (OSError, ValueError, KeyError, TypeError):
            raise RuntimeError("Local embeddings unavailable. Check OBSIDIAN_OLLAMA_URL and the installed OBSIDIAN_EMBED_MODEL.") from None
