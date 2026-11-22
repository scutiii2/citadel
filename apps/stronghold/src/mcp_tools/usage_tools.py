"""MCP usage summaries limited to the requesting account."""

from typing import Any

from src.mcp_tools.scope import Account
from src.usage.service import UsageService


class UsageTools:
    def __init__(self, usage: UsageService) -> None:
        self._usage = usage

    async def summary(self, account: Account, days: int, group_by: str) -> dict[str, Any]:
        if not 1 <= days <= 90:
            return {"ok": False, "message": "Days must be between 1 and 90."}
        if group_by not in {"agent", "model", "day"}:
            return {"ok": False, "message": "Group by agent, model or day."}
        report = await self._usage.report(account.uid, days, group_by="agent" if group_by == "day" else group_by)
        if group_by == "day":
            rows = [{"key": day["date"], "total_tokens": day["tokens"]} for day in report["daily"]]
        else:
            rows = [
                {"key": group["key"], "total_tokens": group["tokens"], "input_tokens": group["input_tokens"],
                 "output_tokens": group["output_tokens"], "requests": group["turns"]}
                for group in report["groups"]
            ]
        requests, tokens = report["turns"], report["total_tokens"]
        return {
            "ok": True, "days": days, "group_by": group_by, "requests": requests, "total_tokens": tokens, "rows": rows,
            "message": f"{requests} answers, {tokens} tokens in the last {days} days, by {group_by} (your own usage).",
        }
