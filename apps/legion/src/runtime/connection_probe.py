"""Reachability check for the Connections page: one MCP server, changing nothing.

The check asks each address for any answer and reports `{ok, message, code?, origins?}`; `code` is the HTTP status of a refusal, or NET, TIME, GONE, STDIO. A token is only sent to the address it belongs to, and
never appears in a result.
"""

from __future__ import annotations

from typing import Any

import httpx

from src.runtime import outside_origins

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
# Tests replace this to answer without a network.
_TRANSPORT: httpx.AsyncBaseTransport | None = None


async def _get(address: str, headers: dict[str, str]) -> httpx.Response | tuple[str, str]:
    """The answer to one GET, or `(code, reason)` when there was none."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=_TRANSPORT, follow_redirects=False) as client:
            return await client.get(address, headers=headers)
    except httpx.TimeoutException:
        return "TIME", "No answer within 5 seconds."
    except httpx.HTTPError:
        return "NET", "Could not connect to this address."


async def probe_server(entry: dict[str, Any]) -> dict[str, Any]:
    """Any HTTP answer below 500 from each address of an MCP server shows it is up; 401 and 403 mean the token is refused."""
    if entry.get("transport") != "http":
        return {"ok": False, "code": "STDIO", "message": "Only http connections can be tested from here.", "origins": []}
    auth = entry.get("auth") if isinstance(entry.get("auth"), dict) else {}
    path = entry.get("path") or "/mcp"
    targets: list[tuple[str, str | None]] = []
    if isinstance(entry.get("url"), str):
        targets.append((entry["url"], None))
    for ref in entry.get("origins", []):
        address = outside_origins.origin_address(ref["origin_id"])
        targets.append((address + path if address else "", ref.get("header_value")))
    results = []
    for address, own_token in targets:
        if not address:
            results.append({"ok": False, "code": "GONE", "message": "This address left Treasury's catalog."})
            continue
        token = own_token or auth.get("header_value")
        headers = {auth["header_name"]: token} if auth.get("type") == "header" and auth.get("header_name") and token else {}
        answer = await _get(address, headers)
        if isinstance(answer, tuple):
            results.append({"ok": False, "code": answer[0], "message": answer[1]})
        elif answer.status_code in (401, 403):
            results.append({"ok": False, "code": str(answer.status_code), "message": "The token was refused."})
        elif answer.status_code >= 500:
            results.append({"ok": False, "code": str(answer.status_code), "message": f"The server answered {answer.status_code}."})
        else:
            results.append({"ok": True, "message": "The server answers."})
    ok = bool(results) and all(result["ok"] for result in results)
    failed = next((result for result in results if not result["ok"]), None)
    return {"ok": ok, "message": "Every address answers." if ok else "Some addresses do not answer.",
            **({"code": failed["code"]} if failed else {}), "origins": results}
