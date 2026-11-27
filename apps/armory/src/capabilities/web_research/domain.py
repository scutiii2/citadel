"""Search the web, read pages, map and crawl sites through the engine chain.
Input is checked here before any engine sees it; web text is capped and fenced (`services/untrusted.py`)
before it reaches a model."""

from __future__ import annotations

from collections.abc import Callable

from src.capabilities.web_research.chain import EngineChain, Outcome
from src.capabilities.web_research.contract import (
    CrawlResult,
    MapResult,
    PageResult,
    SearchHit,
    SearchResult,
    SiteLink,
)
from src.services import untrusted
from src.services.public_address import require_public_url

MAX_RESULTS = 10
MAX_PAGE_BYTES = 24_000
MAX_CRAWL_BYTES = 48_000
MAX_MAP_LINKS = 500
MAX_CRAWL_PAGES = 25
MAX_SNIPPET_CHARS = 600
TOPICS = ("general", "news")


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_SNIPPET_CHARS else text[: MAX_SNIPPET_CHARS - 3] + "..."


def _check_limit(limit: int, maximum: int) -> None:
    if not 1 <= limit <= maximum:
        raise ValueError(f"limit must be between 1 and {maximum}, not {limit}")


def _nothing(url: str, outcome: Outcome, what: str) -> str:
    """The message of a result without content."""
    if outcome.missing_status:
        return f"{url} answered {outcome.missing_status} ({outcome.engine}). The page does not exist."
    return f"{url} returned no {what}."


class WebResearchDesk:
    """Web operations over one engine chain. `check_url` refuses addresses that are not public. Calls block."""

    def __init__(self, chain: EngineChain, check_url: Callable[[str], str] = require_public_url) -> None:
        self._chain = chain
        self._check_url = check_url

    def search(self, query: str, max_results: int = 5, topic: str = "general") -> SearchResult:
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        if not 1 <= max_results <= MAX_RESULTS:
            raise ValueError(f"max_results must be between 1 and {MAX_RESULTS}, not {max_results}")
        if topic not in TOPICS:
            raise ValueError(f"topic must be one of {', '.join(TOPICS)}, not {topic!r}")

        def ask(engine, seconds):
            # Built inside the chain, so a malformed reply moves on to the next engine.
            return [
                SearchHit(title=hit.title, url=hit.url, snippet=_snippet(hit.snippet), score=round(hit.score, 3))
                for hit in engine.search(query, max_results, topic, seconds)[:max_results]
            ]

        outcome = self._chain.run("search", ask)
        hits = outcome.value or []
        message = f"{len(hits)} results for {query!r} from {outcome.engine}." if hits else f"No results for {query!r}."
        return SearchResult(query=query, results=hits, message=message)

    def read_page(self, url: str) -> PageResult:
        url = self._check_url(url)
        outcome = self._chain.run("read", lambda engine, seconds: engine.read(url, seconds))
        page = outcome.value
        if page is None:
            return PageResult(url=url, title="", content="", message=_nothing(url, outcome, "readable text"))
        content = untrusted.fenced_and_capped(page.text, source=f"web page {url}", max_bytes=MAX_PAGE_BYTES)
        message = f"Read {url} with {outcome.engine} ({len(page.text)} characters)."
        return PageResult(url=url, title=page.title, content=content, message=message)

    def map_site(self, url: str, limit: int = 100) -> MapResult:
        _check_limit(limit, MAX_MAP_LINKS)
        url = self._check_url(url)

        def ask(engine, seconds):
            return [SiteLink(url=link.url, title=link.title) for link in engine.map(url, limit, seconds)[:limit]]

        outcome = self._chain.run("map", ask)
        links = outcome.value or []
        message = (f"{len(links)} pages found on {url} with {outcome.engine}." if links
                   else _nothing(url, outcome, "page links"))
        return MapResult(url=url, links=links, message=message)

    def crawl_site(self, url: str, limit: int = 10) -> CrawlResult:
        _check_limit(limit, MAX_CRAWL_PAGES)
        url = self._check_url(url)
        outcome = self._chain.run("crawl", lambda engine, seconds: engine.crawl(url, limit, seconds))
        crawl = outcome.value
        if crawl is None:
            return CrawlResult(url=url, status="completed", pages=[], content="",
                               message=_nothing(url, outcome, "readable pages"))
        read = [page for page in crawl.pages if page][:limit]
        joined = "\n\n".join(f"## {page.url}\n{page.text}" for page in read)
        content = untrusted.fenced_and_capped(joined, source=f"crawl of {url}", max_bytes=MAX_CRAWL_BYTES)
        suffix = "" if crawl.complete else " The time ran out before the crawl finished; lower the limit or try again."
        return CrawlResult(
            url=url, status="completed" if crawl.complete else "scraping", pages=[page.url for page in read],
            content=content, message=f"Crawled {len(read)} pages from {url} with {outcome.engine}.{suffix}",
        )
