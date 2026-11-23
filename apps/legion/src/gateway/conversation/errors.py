"""The one error every layer raises. `message` is safe to show: no paths, URLs or credentials."""
from __future__ import annotations


class GatewayError(Exception):
    """`kind` is rate_limit, quota, auth or unavailable for upstream failures a caller may react to, else None."""

    def __init__(self, status: int, code: str, message: str, kind: str | None = None, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.kind, self.retry_after = status, code, message, kind, retry_after

    def body(self) -> dict:
        error = {"code": self.code, "message": self.message}
        if self.kind:
            error["kind"] = self.kind
        return {"error": error}
