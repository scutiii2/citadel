"""Private HTTP transport to Armory's deterministic brain operations."""
import httpx

from src.services.brain_connections import BrainError
from src.services.mcp_server_info import base_url


class BrainGateway:
    def __init__(self, client, mcp_url: str, token: str | None):
        self.client, self.url, self.token = client, base_url(mcp_url) + "/brains/operation", token

    async def operation(self, uid: str, operation: str, scope: str, **arguments) -> dict:
        if not self.token or not uid:
            raise BrainError("Brain transport requires configured internal authentication", 503)
        try:
            response = await self.client.post(self.url,
                headers={"X-Internal-Token": self.token, "X-Requester-Uid": uid},
                json={"operation": operation, "scope": scope, **arguments}, timeout=30, follow_redirects=False)
        except httpx.HTTPError:
            raise BrainError("Brain service is unavailable", 503) from None
        if not response.is_success:
            # Armory exposes only safe errors; never include raw response bodies.
            minimum_version = "Safe promotion requires Obsidian Local REST API 5.2.0 or newer with conditional create support."
            try:
                if response.json().get("error") == minimum_version:
                    raise BrainError(minimum_version, 409)
            except (ValueError, AttributeError):
                pass
            raise BrainError("Brain operation failed. Check connection status and destination access.",
                             response.status_code if response.status_code in (403, 404, 409, 412) else 503)
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except ValueError:
            raise BrainError("Brain service returned an invalid response", 503) from None
