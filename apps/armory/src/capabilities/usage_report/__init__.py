"""Usage report: token usage per agent, model or day, read from ai_agent's usage log."""

from src.services.capability_base import Capability


class UsageReport(Capability):
    id = "usage"
    label = "Usage Report"


CAPABILITY = UsageReport()
