"""LAYAModel: Legion's only connection to Laya, the shared Laya service (Python/LayaModel).

The service owns both Laya models and every local decision strategy; Legion sends it typed questions and
a strategy name (`ask`) and, when it adds the cloud fallback (Jev) as one more voter, asks it to mix that
voter in (`combine`). Set LAYA_SERVICE_URL (and LAYA_TOKEN when the service has one); without the URL no
Laya model is available."""

from __future__ import annotations

import os
from typing import Any

import httpx

TIMEOUT_SECONDS = 60.0


class LayaServiceError(RuntimeError):
    """The service is down, refused the request, or could not answer. `calls` lists the model calls it made;
    `status` is the HTTP status when the service answered at all (422: the request itself was refused)."""

    def __init__(self, message: str, calls: list[dict[str, Any]] | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.calls = calls or []
        self.status = status


class LAYAModel:
    def __init__(self, url: str, token: str = "") -> None:
        self._url = url.rstrip("/")
        self._token = token

    @classmethod
    def from_env(cls) -> "LAYAModel":
        return cls(os.environ.get("LAYA_SERVICE_URL", ""), os.environ.get("LAYA_TOKEN", ""))

    @property
    def configured(self) -> bool:
        return bool(self._url)

    def health(self) -> bool:
        try:
            return httpx.get(f"{self._url}/health", timeout=3.0).is_success
        except httpx.HTTPError:
            return False

    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Token": self._token} if self._token else {}

    def strategies(self) -> dict[str, Any]:
        """The service's strategy names and its default: `{"strategies": [...], "default": "auto"}`."""
        if not self.configured:
            raise LayaServiceError("Laya is not configured: set LAYA_SERVICE_URL")
        try:
            response = httpx.get(f"{self._url}/v1/strategies", headers=self._headers(), timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as error:
            raise LayaServiceError(f"The Laya service could not be reached: {error}") from error
        if not response.is_success:
            raise LayaServiceError(f"The Laya service refused the request ({response.status_code})", status=response.status_code)
        body = response.json()
        return {"strategies": list(body["strategies"]), "default": body.get("default")}

    def _post(self, path: str, body: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        if not self.configured:
            raise LayaServiceError("Laya is not configured: set LAYA_SERVICE_URL")
        try:
            response = httpx.post(f"{self._url}{path}", headers=self._headers(), json=body,
                                  timeout=TIMEOUT_SECONDS if timeout is None else min(timeout, TIMEOUT_SECONDS))
        except httpx.HTTPError as error:
            raise LayaServiceError(f"The Laya service could not be reached: {error}") from error
        if response.is_success:
            return response.json()
        detail = response.json().get("detail") if response.headers.get("content-type", "").startswith("application/json") else None
        if isinstance(detail, dict):
            raise LayaServiceError(detail.get("message", "The Laya service could not answer"), detail.get("calls"), response.status_code)
        if response.status_code == 422 and isinstance(detail, str):
            raise LayaServiceError(detail, status=422)
        raise LayaServiceError(f"The Laya service refused the request ({response.status_code}): {detail or response.text[:200]}",
                               status=response.status_code)

    def validate(self, questions: dict[str, Any]) -> None:
        """Raises LayaServiceError (status 422, `str(error)` says what is wrong) unless the service accepts the questions."""
        self._post("/v1/validate", {"questions": questions})

    def ask(self, strategy: str, text: str, questions: dict[str, Any], max_len: int,
            *, timeout: float | None = None, **tuning: Any) -> dict[str, Any]:
        """The service's answer: `answers` by question id (full, with `rounds`, `options` and `voters`), `uncertain`
        and `calls`. `tuning` may hold min_confidence, thresholds, prune_ratio and pair_ratio."""
        body = {"strategy": strategy, "text": text, "questions": questions, "max_len": max_len, "trace": True,
                **{key: value for key, value in tuning.items() if value is not None}}
        return self._post("/v1/ask", body, timeout=timeout)

    def combine(self, voters: dict[str, Any], options: list[str], prune_ratio: float, pair_ratio: float) -> dict[str, Any]:
        """`voters` over `options` (renormalised), their `average`, the `kept` options and, with two voters or more, `final`."""
        return self._post("/v1/combine", {"voters": voters, "options": options,
                                          "prune_ratio": prune_ratio, "pair_ratio": pair_ratio})


_agent: LAYAModel | None = None


def agent() -> LAYAModel:
    """The process-wide client, built from the environment on first use."""
    global _agent
    if _agent is None or _agent._url != os.environ.get("LAYA_SERVICE_URL", "").rstrip("/"):
        _agent = LAYAModel.from_env()
    return _agent


def configured() -> bool:
    return agent().configured
