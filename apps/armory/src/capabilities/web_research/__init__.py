"""Web research: search the web and read a page through Tavily."""

from src.services.capability_base import Capability


class WebResearch(Capability):
    id = "web"
    label = "Web Research"


CAPABILITY = WebResearch()
