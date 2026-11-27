"""What every web engine shares: its interface, the plain data it returns, its errors and a JSON request helper.

Engines return web text as it came; `domain.py` caps and fences it."""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import ClassVar

from src.citadel_auth.failure import Code

MISSING_STATUSES = (404, 410)


@dataclass(frozen=True)
class Hit:
    title: str
    url: str
    snippet: str
    score: float = 0.0


@dataclass(frozen=True)
class Page:
    """One page's text. False when it holds no readable text."""

    url: str
    text: str
    title: str = ""

    def __bool__(self) -> bool:
        return bool(self.text.strip())


@dataclass(frozen=True)
class Link:
    url: str
    title: str = ""


@dataclass(frozen=True)
class Crawl:
    """Pages of one crawl. `complete` is False when the time ran out first. False when no page holds text."""

    pages: tuple[Page, ...]
    complete: bool = True

    def __bool__(self) -> bool:
        return any(self.pages)


class EngineError(Exception):
    """The engine could not do the job; the next one may. `reason` goes to the server log and never holds a key."""

    def __init__(self, code: Code, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class PageMissing(Exception):
    """The page itself answered that it does not exist: no other engine is asked."""

    def __init__(self, status: int) -> None:
        super().__init__(f"page answered {status}")
        self.status = status


class Engine:
    """One way to reach the web. `operations` names the methods it supports; `timeout` is in seconds. Calls block."""

    name: str
    operations: ClassVar[frozenset[str]] | frozenset[str] = frozenset()

    def configured(self) -> bool:
        return True

    def search(self, query: str, max_results: int, topic: str, timeout: float) -> list[Hit]:
        raise NotImplementedError

    def read(self, url: str, timeout: float) -> Page:
        raise NotImplementedError

    def map(self, url: str, limit: int, timeout: float) -> list[Link]:
        raise NotImplementedError

    def crawl(self, url: str, limit: int, timeout: float) -> Crawl:
        raise NotImplementedError


def json_request(engine: str, method: str, url: str, token: str, body: dict | None, timeout: float) -> dict:
    """One JSON request to an engine's API; every failure becomes an `EngineError`."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        request = urllib.request.Request(
            url, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - address comes from config, not a caller
            data = json.loads(response.read())
    except urllib.error.HTTPError as error:
        code = Code.DEP_AUTH_REJECTED if error.code in (401, 403) else Code.DEP_ERROR
        raise EngineError(code, f"{engine} answered HTTP {error.code}") from error
    except TimeoutError as error:
        raise EngineError(Code.DEP_TIMEOUT, f"{engine} timed out") from error
    except urllib.error.URLError as error:
        code = Code.DEP_TIMEOUT if isinstance(error.reason, TimeoutError) else Code.DEP_UNAVAILABLE
        raise EngineError(code, f"{engine} could not be reached: {error.reason}") from error
    except (OSError, http.client.HTTPException) as error:
        raise EngineError(Code.DEP_UNAVAILABLE, f"{engine} could not be reached: {type(error).__name__}") from error
    except ValueError as error:
        raise EngineError(Code.DEP_ERROR, f"{engine} sent an unreadable reply") from error
    if not isinstance(data, dict):
        raise EngineError(Code.DEP_ERROR, f"{engine} sent an unreadable reply")
    return data
