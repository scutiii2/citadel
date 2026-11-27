"""Runs one Scrapy job in its own process: a JSON job on stdin, a JSON answer on stdout.

It opens caller-chosen addresses, so two guards apply. Every request URL (the first, each link, each redirect,
literal IP addresses included) is checked in a downloader middleware. Every name lookup of the process is checked
again by a replaced `socket.getaddrinfo`, which covers a name that changes its answer between check and connect.
Twisted keeps its own reference to `getaddrinfo`, so Scrapy is imported only after the replacement."""

from __future__ import annotations

import json
import re
import socket
import sys
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urlsplit

from src.services.public_address import ALLOWED_PORTS, is_public_ip, require_public_url

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_PAGE_CHARS = 100_000
MAX_DEPTH = 3
MAX_MAP_PAGES = 20  # pages fetched to build a map: the start page and some one level below
USER_AGENT = "CitadelArmory/1.0 (web research)"
_DROPPED_TAGS = ("script", "style", "nav", "footer", "noscript", "template", "svg")
_BINARY = re.compile(r"\.(7z|avi|bin|bmp|css|dmg|docx?|exe|gif|gz|ico|iso|jpe?g|js|mov|mp[34]|pdf|png|pptx?|rar|"
                     r"svg|tar|tiff?|wav|webm|webp|woff2?|xlsx?|zip)$", re.IGNORECASE)


@dataclass(frozen=True)
class NetworkPolicy:
    """Which addresses and ports may be opened. Only tests pass anything but the default."""

    allows_ip: Callable[[str], bool] = is_public_ip
    ports: Collection[int | None] | None = ALLOWED_PORTS


@dataclass
class Job:
    operation: str
    url: str
    limit: int
    timeout: float
    host: str = ""
    pages: list[dict] = field(default_factory=list)
    links: dict[str, str] = field(default_factory=dict)
    queued: set[str] = field(default_factory=set)
    seen: set[str] = field(default_factory=set)
    missing: int | None = None
    error: str | None = None
    detail: str = ""

    def fail(self, error: str, detail: str) -> None:
        self.error, self.detail = error, detail


def install_guard(policy: NetworkPolicy) -> None:
    original = socket.getaddrinfo

    def guarded(*args, **kwargs):
        results = original(*args, **kwargs)
        if not all(policy.allows_ip(str(result[4][0])) for result in results):
            raise socket.gaierror("non-public address refused")
        return results

    socket.getaddrinfo = guarded


def _markdown(response) -> tuple[str, str]:
    """(title, text) of a text response; HTML becomes Markdown without scripts, styles and page furniture."""
    from scrapy.http import HtmlResponse, TextResponse

    if not isinstance(response, TextResponse):
        return "", ""
    if not isinstance(response, HtmlResponse):
        return "", response.text[:MAX_PAGE_CHARS]
    from bs4 import BeautifulSoup
    from markdownify import MarkdownConverter

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(_DROPPED_TAGS):
        tag.decompose()
    text = MarkdownConverter(heading_style="ATX").convert_soup(soup.body or soup)
    return title, re.sub(r"\n\s*\n+", "\n\n", text).strip()[:MAX_PAGE_CHARS]


def _site_links(response, host: str):
    """(address, anchor text) of each page link that stays on `host`."""
    from scrapy.http import TextResponse

    if not isinstance(response, TextResponse):
        return
    for anchor in response.css("a[href]"):
        try:
            address = urldefrag(response.urljoin(anchor.attrib["href"].strip())).url
            parts = urlsplit(address)
        except ValueError:
            continue
        if parts.scheme in ("http", "https") and parts.hostname == host and not _BINARY.search(parts.path):
            yield address, " ".join(" ".join(anchor.css("::text").getall()).split())[:200]


def _crawl(job: Job, policy: NetworkPolicy) -> str:
    """Run the job and return Scrapy's finish reason."""
    import scrapy
    from scrapy.crawler import CrawlerProcess
    from scrapy.exceptions import CloseSpider, IgnoreRequest

    class AddressGuard:
        def process_request(self, request):
            try:
                require_public_url(request.url, allows_ip=policy.allows_ip, ports=policy.ports,
                                   resolver=socket.getaddrinfo)
            except ValueError as error:
                raise IgnoreRequest(str(error)) from None

    class SiteSpider(scrapy.Spider):
        name = "site"

        async def start(self):
            job.queued.add(job.url)
            yield scrapy.Request(job.url, callback=self.parse, errback=self.start_failed, meta={"is_start": True})

        def parse(self, response):
            is_start = response.meta.get("is_start", False)
            if response.status >= 400:
                if is_start:
                    if response.status in (404, 410):
                        job.missing = response.status
                    else:
                        job.fail("error", f"the page answered {response.status}")
                return
            host = urlsplit(response.url).hostname or ""
            if is_start:
                job.host = host
            elif host != job.host:  # redirected off the start site
                return
            if response.url in job.seen:
                return
            job.seen.add(response.url)
            if job.operation == "map":
                for address, title in _site_links(response, job.host):
                    job.links.setdefault(address, title)
                    if len(job.links) >= job.limit:
                        raise CloseSpider("enough")
                if is_start:
                    yield from self.follow(response, MAX_MAP_PAGES)
                return
            title, text = _markdown(response)
            if text:
                job.pages.append({"url": response.url, "title": title, "text": text})
            if len(job.pages) >= job.limit:
                raise CloseSpider("enough")
            if job.operation == "crawl":
                yield from self.follow(response, job.limit * 3)

        def follow(self, response, most: int):
            for address, _title in _site_links(response, job.host):
                if len(job.queued) >= most:
                    return
                if address not in job.queued:
                    job.queued.add(address)
                    yield scrapy.Request(address, callback=self.parse)

        def start_failed(self, failure):
            if failure.check(IgnoreRequest):  # robots.txt or the address guard
                job.fail("error", str(failure.value) or "robots.txt does not allow this page")
            elif "Timeout" in failure.type.__name__ or "TimedOut" in failure.type.__name__:
                job.fail("timeout", "the page did not answer in time")
            else:
                job.fail("unavailable", f"the page could not be reached ({failure.type.__name__})")

    process = CrawlerProcess(
        {
            "USER_AGENT": USER_AGENT,
            "ROBOTSTXT_OBEY": True,
            "HTTPPROXY_ENABLED": False,
            "RETRY_ENABLED": False,
            "COOKIES_ENABLED": False,
            "HTTPERROR_ALLOW_ALL": True,
            "TELNETCONSOLE_ENABLED": False,
            "LOG_ENABLED": False,
            "REDIRECT_MAX_TIMES": 5,
            "CONCURRENT_REQUESTS": 4,
            "DEPTH_LIMIT": MAX_DEPTH,
            "DEPTH_PRIORITY": 1,  # breadth first
            "SCHEDULER_DISK_QUEUE": "scrapy.squeues.PickleFifoDiskQueue",
            "SCHEDULER_MEMORY_QUEUE": "scrapy.squeues.FifoMemoryQueue",
            "DOWNLOAD_MAXSIZE": MAX_RESPONSE_BYTES,
            # Leave time to answer with what was read before the parent kills the process.
            "CLOSESPIDER_TIMEOUT": job.timeout * 0.7,
            "DOWNLOAD_TIMEOUT": max(1.0, job.timeout * 0.2),
            "TWISTED_DNS_RESOLVER": "scrapy.resolver.CachingHostnameResolver",  # the default skips getaddrinfo
            "DOWNLOAD_HANDLERS": {"data": None, "file": None, "ftp": None, "s3": None},
            "DOWNLOADER_MIDDLEWARES": {AddressGuard: 50},
        },
        install_root_handler=False,
    )
    crawler = process.create_crawler(SiteSpider)
    process.crawl(crawler)
    process.start()
    return str(crawler.stats.get_value("finish_reason") if crawler.stats else "")


def run(raw: dict, policy: NetworkPolicy) -> dict:
    install_guard(policy)
    job = Job(raw["operation"], raw["url"], int(raw["limit"]), float(raw["timeout"]))
    reason = _crawl(job, policy)
    partial = reason == "closespider_timeout"
    if not (job.pages or job.links or job.missing or job.error) and partial:
        job.fail("timeout", "the site did not answer in time")
    return {
        "pages": job.pages[: job.limit],
        "links": [{"url": url, "title": title} for url, title in list(job.links.items())[: job.limit]],
        "missing": job.missing,
        "error": job.error,
        "detail": job.detail,
        "partial": partial,
    }


def main(policy: NetworkPolicy = NetworkPolicy()) -> None:
    answer_to = sys.stdout
    sys.stdout = sys.stderr  # nothing else may mix into the answer
    answer = run(json.loads(sys.stdin.buffer.read()), policy)
    answer_to.write(json.dumps(answer))
    answer_to.flush()


if __name__ == "__main__":
    main()
