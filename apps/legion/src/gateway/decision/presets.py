"""Starting points for the Gateways page: no secrets. A saved gateway is the preset plus the secrets and any edits."""
from __future__ import annotations

from src.gateway.decision.store import TYPESAFE_URL

PRESETS: dict[str, dict] = {
    # Laya model service (DSC_Laya_Model, host port 29220). A container reaches the host as host.docker.internal.
    "laya": {"kind": "scuti", "label": "Laya (local decisions)", "url": "http://host.docker.internal:29220",
             "strategy": "english-then-typed", "window": 4096},
    "jev": {"kind": "typesafe", "label": "Jev (TypeSafe)", "url": TYPESAFE_URL, "model": "jev-latest"},
    "ollama": {"kind": "ollama", "label": "Ollama", "url": "http://host.docker.internal:11434", "model": "qwen3.5:4b"},
    # Router over free provider tiers (AI/ModelEngines/FreeLLMApiService, host port 29652): POST /v1/decisions picks a free
    # decision model itself. Its dashboard is on the same port.
    "freellmapi": {"kind": "freellmapi", "label": "FreeLLMAPI (free decision models)", "url": "http://host.docker.internal:29652"},
}

# Where a kind lists its model names (a link on the Gateways page, opened in a new tab). Links are not checked at run time.
MODEL_LISTS: dict[str, str] = {"ollama": "https://ollama.com/library", "typesafe": "https://docs.typesafe.ai/models"}
