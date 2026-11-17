"""Fresh real assertions for each request made by synchronous route tests."""

from collections.abc import Mapping

from src.citadel_auth.testing import requester_headers, signed

stack = None


class FreshHeaders(Mapping):
    """HTTPX materializes this mapping separately for every request."""

    def __init__(self, *, uid="", username="", email="", caller="portcullis", invalid=False):
        self.uid, self.username, self.email = uid, username, email
        self.caller, self.invalid = caller, invalid

    def _headers(self):
        result = signed(stack[self.caller], "armory") if not self.invalid else {"Authorization": "Bearer invalid"}
        if self.uid:
            result.update(requester_headers(stack["portcullis"], self.uid, self.username, self.email, ["armory", "stronghold", "legion"]))
        return result

    def __getitem__(self, key):
        return self._headers()[key]

    def __iter__(self):
        return iter(self._headers())

    def __len__(self):
        return len(self._headers())

    def items(self):
        return self._headers().items()


def service_auth(caller="portcullis"):
    from src.citadel_auth import ServiceAuth
    return ServiceAuth(stack[caller], "armory")
