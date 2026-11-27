"""Tavily (https://docs.tavily.com): search, extract, map and crawl."""

from __future__ import annotations

from src.capabilities.web_research.engines.base import Crawl, Engine, EngineError, Hit, Link, Page, json_request
from src.citadel_auth.failure import Code

BASE_URL = "https://api.tavily.com"
MAX_DEPTH = 2
MAX_BREADTH = 500


def _clamp(value: float, lowest: float, highest: float) -> float:
    return max(lowest, min(value, highest))


class TavilyEngine(Engine):
    name = "Tavily"
    operations = frozenset({"search", "read", "map", "crawl"})

    def __init__(self, api_key: str, base_url: str = BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def configured(self) -> bool:
        return bool(self._api_key)

    def search(self, query: str, max_results: int, topic: str, timeout: float) -> list[Hit]:
        body = {
            "query": query,
            "max_results": max_results,
            "topic": topic,
            "search_depth": "basic",
            "include_answer": False,  # tools never call an AI; the agent writes the answer
        }
        results = self._post("/search", body, timeout).get("results") or []
        return [
            Hit(item.get("title") or item["url"], item["url"], item.get("content") or "", float(item.get("score") or 0.0))
            for item in results
            if item.get("url")
        ]

    def read(self, url: str, timeout: float) -> Page:
        body = {"urls": [url], "format": "markdown", "timeout": _clamp(timeout, 1, 60)}
        data = self._post("/extract", body, timeout)
        for page in data.get("results") or []:
            return Page(url, page.get("raw_content") or "")
        failed = data.get("failed_results") or []
        if failed:
            raise EngineError(Code.DEP_ERROR, f"{self.name} could not read the page: {str(failed[0].get('error'))[:200]}")
        return Page(url, "")

    def map(self, url: str, limit: int, timeout: float) -> list[Link]:
        results = self._post("/map", self._site_body(url, limit, timeout), timeout).get("results") or []
        return [Link(address) for address in results if isinstance(address, str)]

    def crawl(self, url: str, limit: int, timeout: float) -> Crawl:
        body = {**self._site_body(url, limit, timeout), "format": "markdown"}
        results = self._post("/crawl", body, timeout).get("results") or []
        return Crawl(tuple(Page(item.get("url") or url, item.get("raw_content") or "") for item in results[:limit]))

    @staticmethod
    def _site_body(url: str, limit: int, timeout: float) -> dict:
        return {
            "url": url,
            "limit": limit,
            "max_depth": MAX_DEPTH,
            "max_breadth": min(limit, MAX_BREADTH),
            "allow_external": False,  # Tavily's default would leave the site
            "timeout": _clamp(timeout, 10, 150),
        }

    def _post(self, path: str, body: dict, timeout: float) -> dict:
        return json_request(self.name, "POST", self._base_url + path, self._api_key, body, timeout)
