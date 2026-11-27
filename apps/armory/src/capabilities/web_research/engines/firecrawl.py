"""Firecrawl's v2 API (https://docs.firecrawl.dev/api-reference): the hosted service, and Firecrawl Local without search."""

from __future__ import annotations

import time
from contextlib import suppress
from urllib.parse import quote

from src.capabilities.web_research.engines.base import (
    MISSING_STATUSES,
    Crawl,
    Engine,
    EngineError,
    Hit,
    Link,
    Page,
    PageMissing,
    json_request,
)
from src.citadel_auth.failure import Code

HOSTED_URL = "https://api.firecrawl.dev"
POLL_SECONDS = 2.0
MIN_REQUEST_SECONDS = 5.0
_SITE_OPERATIONS = frozenset({"read", "map", "crawl"})


class FirecrawlEngine(Engine):
    """One Firecrawl server. Build it with `hosted` or `local`."""

    def __init__(self, name: str, base_url: str, token: str, *, ready: bool, searches: bool) -> None:
        self.name = name
        self.operations = _SITE_OPERATIONS | {"search"} if searches else _SITE_OPERATIONS
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._ready = ready

    @classmethod
    def hosted(cls, api_key: str) -> FirecrawlEngine:
        return cls("Firecrawl", HOSTED_URL, api_key, ready=bool(api_key), searches=True)

    @classmethod
    def local(cls, base_url: str, token: str) -> FirecrawlEngine:
        return cls("Firecrawl Local", base_url, token, ready=bool(base_url), searches=False)

    def configured(self) -> bool:
        return self._ready

    def search(self, query: str, max_results: int, topic: str, timeout: float) -> list[Hit]:
        body: dict = {"query": query, "limit": max_results, "sources": ["web"]}
        if topic == "news":
            body["tbs"] = "qdr:w"
        results = (self._request("POST", "/v2/search", body, timeout).get("data") or {}).get("web") or []
        return [
            Hit(item.get("title") or item["url"], item["url"], item.get("description") or "")
            for item in results
            if item.get("url")
        ]

    def read(self, url: str, timeout: float) -> Page:
        body = {"url": url, "formats": ["markdown"], "onlyMainContent": True}
        data = self._request("POST", "/v2/scrape", body, timeout).get("data") or {}
        meta = data.get("metadata") or {}
        status = meta.get("statusCode")
        if status in MISSING_STATUSES:
            raise PageMissing(status)
        if isinstance(status, int) and status >= 400:
            raise EngineError(Code.DEP_ERROR, f"{self.name}: the page answered {status}")
        return Page(url, data.get("markdown") or "", meta.get("title") or "")

    def map(self, url: str, limit: int, timeout: float) -> list[Link]:
        links = self._request("POST", "/v2/map", {"url": url, "limit": limit}, timeout).get("links") or []
        items = ({"url": link} if isinstance(link, str) else link for link in links)
        return [Link(item["url"], item.get("title") or "") for item in items if item.get("url")]

    def crawl(self, url: str, limit: int, timeout: float) -> Crawl:
        deadline = time.monotonic() + timeout
        body = {"url": url, "limit": limit, "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True}}
        job = self._request("POST", "/v2/crawl", body, timeout).get("id")
        if not job:
            raise EngineError(Code.DEP_ERROR, f"{self.name} did not return a crawl id")
        path = f"/v2/crawl/{quote(str(job), safe='')}"
        items: list[dict] = []
        status = "scraping"
        try:
            while True:
                remaining = deadline - time.monotonic()
                state = self._request("GET", path, None, max(remaining, MIN_REQUEST_SECONDS))
                status = state.get("status", "scraping")
                items = state.get("data") or items
                if status != "scraping" or remaining <= POLL_SECONDS:
                    break
                time.sleep(POLL_SECONDS)
        except EngineError:
            if not self._pages(items):
                self._cancel(path)
                raise
        if status == "failed":
            raise EngineError(Code.DEP_ERROR, f"{self.name} reported a failed crawl")
        complete = status == "completed"
        statuses = [(item.get("metadata") or {}).get("statusCode") for item in items]
        if complete and statuses and all(code in MISSING_STATUSES for code in statuses):
            raise PageMissing(statuses[0])
        crawl = Crawl(self._pages(items)[:limit], complete)
        if not crawl and not complete:
            self._cancel(path)  # the next engine takes over; stop paying for this job
        return crawl

    @staticmethod
    def _pages(items: list[dict]) -> tuple[Page, ...]:
        pages = []
        for item in items:
            meta = item.get("metadata") or {}
            code = meta.get("statusCode")
            text = item.get("markdown") or ""
            if text.strip() and not (isinstance(code, int) and code >= 400):
                pages.append(Page(meta.get("sourceURL") or meta.get("url") or "(unknown address)", text))
        return tuple(pages)

    def _cancel(self, path: str) -> None:
        with suppress(EngineError):
            self._request("DELETE", path, None, MIN_REQUEST_SECONDS)

    def _request(self, method: str, path: str, body: dict | None, timeout: float) -> dict:
        data = json_request(self.name, method, self._base_url + path, self._token, body, timeout)
        if data.get("success") is False:
            raise EngineError(Code.DEP_ERROR, f"{self.name} failed: {str(data.get('error') or 'unknown error')[:200]}")
        return data
