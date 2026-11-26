"""A server's question that Legion relays, cut to sizes a browser should show. Legion checks the form
and the answer; this only keeps a misbehaving agent from sending the browser anything large or odd."""

from __future__ import annotations

from typing import Any

MAX_FIELDS = 10
MAX_OPTIONS = 20
ID_MAX = 64
LABEL_MAX = 80
DESCRIPTION_MAX = 200
TOOL_MAX = 120
MESSAGE_MAX = 2_000
TEXT_MAX = 2_000
URL_MAX = 2_048
_KINDS = ("text", "number", "integer", "boolean", "choice", "multi_choice")


def _cut(value: Any, limit: int) -> str:
    return value[:limit] if isinstance(value, str) else ""


def clamp_request(event: dict[str, Any]) -> dict[str, Any]:
    """An `elicitation_request` event with only the known keys, bounded."""
    out: dict[str, Any] = {
        "type": "elicitation_request",
        "id": _cut(event.get("id"), ID_MAX),
        "server": _cut(event.get("server"), LABEL_MAX),
        "tool": _cut(event.get("tool"), TOOL_MAX),
        "mode": "url" if event.get("mode") == "url" else "form",
        "message": _cut(event.get("message"), MESSAGE_MAX),
    }
    for key in ("agent_id", "agent_label"):
        if event.get(key):
            out[key] = _cut(event[key], TOOL_MAX)
    if out["mode"] == "url":
        url = event.get("url")
        safe = isinstance(url, str) and len(url) <= URL_MAX and url.lower().startswith("https://")
        out["url"] = url if safe else ""
    else:
        out["fields"] = _fields(event.get("fields"))
    return out


def _fields(raw: Any) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for item in raw[:MAX_FIELDS] if isinstance(raw, list) else []:
        if not isinstance(item, dict) or item.get("kind") not in _KINDS or not _cut(item.get("name"), LABEL_MAX):
            continue
        name = _cut(item["name"], LABEL_MAX)
        field: dict[str, Any] = {
            "name": name, "label": _cut(item.get("label"), LABEL_MAX) or name,
            "kind": item["kind"], "required": item.get("required") is True,
        }
        if description := _cut(item.get("description"), DESCRIPTION_MAX):
            field["description"] = description
        for key in ("min", "max", "max_length"):
            value = item.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                field[key] = value
        if item["kind"] in ("choice", "multi_choice"):
            options = item.get("options") if isinstance(item.get("options"), list) else []
            field["options"] = [
                {"value": o["value"][:LABEL_MAX], "label": _cut(o.get("label"), LABEL_MAX) or o["value"][:LABEL_MAX]}
                for o in options[:MAX_OPTIONS] if isinstance(o, dict) and isinstance(o.get("value"), str)
            ]
        fields.append(field)
    return fields
