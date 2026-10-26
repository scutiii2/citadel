"""Web scraping: scrape a page, map a site and crawl it through Firecrawl."""

from src.services.capability_base import Capability


class Firecrawl(Capability):
    id = "scrape"
    label = "Web Scraping"


CAPABILITY = Firecrawl()
