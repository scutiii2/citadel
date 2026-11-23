"""The one error every layer raises. `message` is safe to show: no paths, URLs, credentials or upstream text."""
from __future__ import annotations


class GatewayError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.retry_after = status, code, message, retry_after
