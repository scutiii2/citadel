"""Current Portcullis permissions for Stronghold Brain routes."""

from fastapi import Depends, HTTPException, Request, status

from src.platform import PlatformError
from src.requester import Requester, current_requester


async def permissions(request: Request, who: Requester = Depends(current_requester)) -> set[str]:
    """What the account may do now. Refused for an account that is unknown, inactive or unverified."""
    try:
        granted = await request.app.state.platform.permissions(who.uid)
    except PlatformError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Portcullis is unavailable") from None
    if granted is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A valid signed-in requester is required")
    return granted


def need(granted: set[str], permission: str) -> None:
    if permission not in granted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")

