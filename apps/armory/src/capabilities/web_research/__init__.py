"""Web research: search the web, read pages, map and crawl sites, with fallback between engines."""

from src.services.capability_base import Capability


class WebResearch(Capability):
    id = "web"
    label = "Web Research"


CAPABILITY = WebResearch()
