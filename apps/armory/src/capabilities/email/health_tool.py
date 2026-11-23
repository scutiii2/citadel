"""Register the readiness probe independently of the Email switch."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from src.capabilities.email import domain
from src.capabilities.email.contract import HealthResult
from src.offload import offload


@offload
def tool_email_checkHealth() -> HealthResult:
    """Check SMTP readiness without sending mail."""
    return domain.desk.health()


def register_health_tool(mcp: FastMCP) -> None:
    mcp.add_tool(
        tool_email_checkHealth,
        meta={"hidden": True, "display_label": "Checking email readiness"},
        annotations=ToolAnnotations(readOnlyHint=True),
    )
