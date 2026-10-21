"""Small, config-driven Local REST API client, modeled on notes/utils/gateway.py.

Unlike the notes gateway, errors never include remote response text or exception
details: those can contain the configured address, authorization, or vault content.
"""

from __future__ import annotations

import json
import math
import re
import ssl
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from src.utils.catalog import catalog

MAX_RESPONSE_BYTES = 2_000_000
MAX_HITS = 50


class ObsidianGatewayError(Exception):
    """A safe message for the caller to relay verbatim."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@catalog
def vault_path(path: str, *, folder: bool = False, markdown: bool = False) -> str:
    """Validate a literal vault-relative POSIX path before URL encoding it.

    Percent escapes are refused rather than decoded: this prevents ambiguous or
    repeatedly encoded traversal from changing meaning in an HTTP intermediary.
    Colons also exclude Windows drive-relative paths and alternate data streams.
    """
    invalid = (
        path.startswith(("/", "\\"))
        or any(char in path for char in ("\\", ":", "%"))
        or any(ord(char) < 32 or ord(char) == 127 for char in path)
    )
    value = path[:-1] if folder and path.endswith("/") else path
    if value:
        invalid = invalid or any(part in {"", ".", ".."} for part in value.split("/"))
    elif not folder or path:
        invalid = True
    if invalid:
        raise ObsidianGatewayError("Use a vault-relative path with / separators, without absolute paths, .. or encoded segments.")
    if markdown and not value.lower().endswith(".md"):
        raise ObsidianGatewayError("Note targets must be vault-relative .md paths.")
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib otherwise forwards Authorization when following some redirects.
        return None


@catalog
class ObsidianGateway:
    """HTTPS/Bearer client with bounded responses, timeout and opt-in writes/TLS bypass."""

    def __init__(
        self, base_url: str, api_key: str, timeout: float = 5.0,
        *, verify_tls: bool = True, allow_write: bool = False, personal: bool = False,
    ) -> None:
        try:
            url = urlsplit(base_url)
            valid = (
                url.scheme == "https" and url.hostname and url.port != 0
                and not url.username and not url.password and not url.query and not url.fragment
                and not any(char.isspace() for char in base_url)
            )
        except ValueError:
            valid = False
        if not valid:
            raise ObsidianGatewayError("Set OBSIDIAN_BASE_URL to an HTTPS URL without credentials, query or fragment.")
        if not api_key.strip() or any(ord(char) < 32 or ord(char) == 127 for char in api_key):
            raise ObsidianGatewayError("Set OBSIDIAN_API_KEY to the Local REST API plugin's Bearer API key.")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ObsidianGatewayError("OBSIDIAN_TIMEOUT must be a positive number of seconds.")
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._timeout = timeout
        self._allow_write = allow_write is True
        context = ssl.create_default_context()
        if verify_tls is False:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        from src.capabilities.obsidian.utils.network import PinnedHTTPSHandler
        self._opener = urllib.request.build_opener(
            PinnedHTTPSHandler(context=context, personal=personal), urllib.request.ProxyHandler({}), _NoRedirect())

    def list(self, folder: str = "") -> list[str]:
        path = vault_path(folder, folder=True)
        data = self._json("GET", "/vault/" + (quote(path, safe="/") + "/" if path else ""))
        if not isinstance(data, dict) or not isinstance(data.get("files"), list):
            raise ObsidianGatewayError("Obsidian returned an invalid response for the folder listing.")
        if not all(isinstance(item, str) for item in data["files"]):
            raise ObsidianGatewayError("Obsidian returned an invalid response for the folder listing.")
        return data["files"]

    def search(self, query: str) -> list[dict[str, Any]]:
        if not query.strip():
            raise ObsidianGatewayError("Say what to search for.")
        params = urlencode({"query": query, "contextLength": 100, "maxResults": MAX_HITS, "maxMatchesPerFile": 3})
        data = self._json("POST", "/search/simple/?" + params)
        if not isinstance(data, list) or not all(
            isinstance(hit, dict) and isinstance(hit.get("filename"), str)
            and isinstance(hit.get("matches"), list)
            and all(isinstance(match, dict) and isinstance(match.get("context"), str) for match in hit["matches"])
            for hit in data
        ):
            raise ObsidianGatewayError("Obsidian returned an invalid response for the search.")
        return data

    def read(self, path: str) -> str:
        target = vault_path(path, markdown=True)
        raw = self._send("GET", "/vault/" + quote(target, safe="/"), accept="text/markdown")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ObsidianGatewayError("Obsidian returned an invalid response: the note is not UTF-8 text.") from None

    def write(self, path: str, text: str, *, overwrite: bool = False) -> None:
        self._write("PUT", path, text, overwrite=overwrite)

    def require_create_only(self) -> None:
        """Promotion requires the plugin's documented conditional-write contract.

        See obsidian-local-rest-api 5.2 OpenAPI, Conditional writes. Older or
        unrecognized servers are refused rather than relying on a racy GET/PUT.
        """
        details = self._json("GET", "/")
        versions = details.get("versions") if isinstance(details, dict) else None
        version = versions.get("self", "") if isinstance(versions, dict) else ""
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\+[^\s]+)?", str(version))
        if match is None or tuple(map(int, match.groups())) < (5, 2, 0):
            raise ObsidianGatewayError("Safe promotion requires Obsidian Local REST API 5.2.0 or newer with conditional create support.")

    def append(self, path: str, text: str) -> None:
        self._write("POST", path, text)

    def _write(self, method: str, path: str, text: str, *, overwrite: bool = False) -> None:
        target = vault_path(path, markdown=True)
        if not self._allow_write:
            raise ObsidianGatewayError("Obsidian writes are disabled: set allow_write (OBSIDIAN_ALLOW_WRITE=true) in server config.")
        endpoint = "/vault/" + quote(target, safe="/")
        create_only = method == "PUT" and not overwrite
        if create_only:
            # Probe for compatibility with older plugin releases. Also send the
            # atomic condition so a concurrent creator cannot be overwritten on
            # plugin versions supporting If-None-Match.
            try:
                self._send("GET", endpoint, accept="text/markdown")
            except ObsidianGatewayError as error:
                if error.status != 404:
                    raise
            else:
                raise ObsidianGatewayError("The Obsidian note already exists. Set overwrite=true to replace it.", status=412)
        self._send(method, endpoint, text=text, create_only=create_only)

    def _json(self, method: str, path: str) -> Any:
        try:
            return json.loads(self._send(method, path))
        except (ValueError, UnicodeDecodeError):
            raise ObsidianGatewayError("Obsidian returned an invalid response: expected JSON.") from None

    def _send(
        self, method: str, path: str, *, text: str | None = None,
        accept: str = "application/json", create_only: bool = False,
    ) -> bytes:
        headers = {"Authorization": f"Bearer {self._key}", "Accept": accept}
        if create_only:
            headers["If-None-Match"] = "*"
        if text is not None:
            headers["Content-Type"] = "text/markdown; charset=utf-8"
        request = urllib.request.Request(
            self._base + path, data=text.encode("utf-8") if text is not None else None, headers=headers, method=method,
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ObsidianGatewayError("Obsidian's response exceeds the 2 MB safety limit. Use a smaller folder or search.")
                return raw
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            message = {
                401: "Obsidian rejected the API key. Check OBSIDIAN_API_KEY.",
                403: "Obsidian refused access to this operation.",
                404: "Obsidian note or folder not found.",
                412: "The Obsidian note already exists or changed. Set overwrite=true to replace it.",
                429: "Obsidian received too many requests. Try again later.",
            }.get(code, "Obsidian refused a redirect." if 300 <= code < 400 else f"Obsidian answered HTTP {code}.")
            raise ObsidianGatewayError(message, status=code) from None
        except (urllib.error.URLError, OSError) as error:
            reason = error.reason if isinstance(error, urllib.error.URLError) else error
            if isinstance(reason, ssl.SSLError):
                message = "Obsidian TLS verification failed. Trust the plugin certificate or explicitly set OBSIDIAN_VERIFY_TLS=false."
            elif isinstance(reason, TimeoutError):
                message = "Obsidian request timed out. Check that Obsidian and the Local REST API plugin are running."
            else:
                message = "Could not reach Obsidian. Check the Local REST API plugin and OBSIDIAN_BASE_URL."
            raise ObsidianGatewayError(message) from None
