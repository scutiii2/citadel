"""Scrapy, the last engine: no key and no outside service. Each call runs `scrapy_worker` in its own process,
because Scrapy's reactor cannot restart and its address guard patches the whole process."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from src.capabilities.web_research.engines.base import Crawl, Engine, EngineError, Link, Page, PageMissing
from src.citadel_auth.failure import Code

logger = logging.getLogger(__name__)

WORKER = "src.capabilities.web_research.engines.scrapy_worker"
ARMORY_ROOT = Path(__file__).resolve().parents[4]
_ERRORS = {"timeout": Code.DEP_TIMEOUT, "unavailable": Code.DEP_UNAVAILABLE}


class ScrapyEngine(Engine):
    name = "Scrapy"
    operations = frozenset({"read", "map", "crawl"})

    def read(self, url: str, timeout: float) -> Page:
        pages = self._run("read", url, 1, timeout)["pages"]
        return Page(url, pages[0]["text"], pages[0]["title"]) if pages else Page(url, "")

    def map(self, url: str, limit: int, timeout: float) -> list[Link]:
        return [Link(item["url"], item["title"]) for item in self._run("map", url, limit, timeout)["links"]]

    def crawl(self, url: str, limit: int, timeout: float) -> Crawl:
        answer = self._run("crawl", url, limit, timeout)
        pages = tuple(Page(item["url"], item["text"], item["title"]) for item in answer["pages"])
        return Crawl(pages, complete=not answer["partial"])

    def _run(self, operation: str, url: str, limit: int, timeout: float) -> dict:
        job = {"operation": operation, "url": url, "limit": limit, "timeout": timeout}
        env = {name: value for name, value in os.environ.items() if not name.lower().endswith("_proxy")}
        try:
            done = subprocess.run(  # noqa: S603 - fixed command; the job travels on stdin
                [sys.executable, "-m", WORKER], input=json.dumps(job).encode(), capture_output=True,
                timeout=timeout, cwd=ARMORY_ROOT, env=env, check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise EngineError(Code.DEP_TIMEOUT, f"{self.name} timed out") from error
        except OSError as error:
            raise EngineError(Code.DEP_UNAVAILABLE, f"{self.name} could not start") from error
        try:
            answer = json.loads(done.stdout)
        except ValueError as error:
            logger.error("Scrapy worker exit %s: %s", done.returncode, done.stderr.decode(errors="replace")[-2000:])
            raise EngineError(Code.DEP_ERROR, f"{self.name} worker failed") from error
        if answer["missing"]:
            raise PageMissing(answer["missing"])
        if answer["error"] and not (answer["pages"] or answer["links"]):
            code = _ERRORS.get(answer["error"], Code.DEP_ERROR)
            raise EngineError(code, f"{self.name}: {answer['detail']}")
        return answer
