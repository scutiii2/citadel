"""Start, stop, restart and list Docker containers on this host via the mounted Docker socket.
The client is built per call so a missing socket fails one tool call, not server startup."""

from __future__ import annotations

import docker
from docker.errors import DockerException, ImageNotFound, NotFound

from src.capabilities.server_manager.contract import (
    AppActionResult,
    AppInfo,
    AppListResult,
    AppLogsResult,
    AppLogTextResult,
)
from src.capabilities.server_manager.utils.redact import redact
from src.capabilities.server_manager.utils.server_watcher import ServerWatcher
from src.services import downloads, identity_context

MAX_LOG_LINES = 5000
MAX_READ_LINES = 300
MAX_READ_CHARS = 20_000


class DockerHost:
    """The Docker daemon this server manages; stateless, so one instance (``host``) serves every call."""

    def _client(self) -> docker.DockerClient:
        try:
            return docker.from_env()
        except DockerException as error:
            raise RuntimeError(
                "Could not reach Docker from this process. If this server is running "
                "in its own container (see zima_host.yaml), make sure the host's "
                "Docker socket is bind-mounted in: add "
                "'/var/run/docker.sock:/var/run/docker.sock' to that service's "
                f"volumes. ({error})"
            ) from error

    def _known_app_names(self, client: docker.DockerClient) -> list[str]:
        return sorted(container.name for container in client.containers.list(all=True))

    @staticmethod
    def _image_label(container) -> str:
        """The image's own tag if it has one, else its short id (a dangling image would otherwise show no name)."""
        try:
            image = container.image
        except ImageNotFound:
            # The image record is gone (pruned, or the daemon cannot resolve it): use the name the container was created with.
            return container.attrs["Config"]["Image"]
        return image.tags[0] if image.tags else image.short_id

    def _get_container(self, client: docker.DockerClient, name: str):
        try:
            return client.containers.get(name)
        except NotFound as error:
            known = self._known_app_names(client)
            raise KeyError(
                f"No app named {name!r} exists on this host. "
                f"{'Apps available: ' + ', '.join(known) + '.' if known else 'No apps found at all.'}"
            ) from error

    def _act(self, name: str, action: str, verb: str) -> AppActionResult:
        client = self._client()
        container = self._get_container(client, name)
        getattr(container, action)()
        container.reload()
        return AppActionResult(
            name=name,
            action=action,
            status=container.status,
            message=f"{name} {verb} - it is now {container.status}.",
        )

    def start_app(self, name: str) -> AppActionResult:
        return self._act(name, "start", "started")

    def stop_app(self, name: str) -> AppActionResult:
        return self._act(name, "stop", "stopped")

    def restart_app(self, name: str) -> AppActionResult:
        return self._act(name, "restart", "restarted")

    @staticmethod
    def _fit(data: bytes) -> tuple[bytes, bool]:
        """The newest part of `data` that fits one download, cut at a line start."""
        if len(data) <= downloads.MAX_FILE_BYTES:
            return data, False
        tail = data[-downloads.MAX_FILE_BYTES :]
        newline = tail.find(b"\n")
        return (tail[newline + 1 :] if newline != -1 else tail), True

    def get_app_logs(self, name: str, lines: int = 500) -> AppLogsResult:
        """The last `lines` log lines of an app as a file the caller can download.
        The file is offered only to the account that asked (see services/downloads.py)."""
        if not 1 <= lines <= MAX_LOG_LINES:
            raise ValueError(f"lines must be between 1 and {MAX_LOG_LINES}, not {lines}")
        container = self._get_container(self._client(), name)
        raw = container.logs(tail=lines, timestamps=True)
        data, trimmed = self._fit(raw)
        count = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        if not data:
            return AppLogsResult(name=name, lines=0, message=f"{name} has no log output.")
        owner = identity_context.current_username()
        try:
            offer = downloads.registry.offer(owner, f"{name}-logs.log", data)
        except downloads.DownloadRefused as error:
            return AppLogsResult(name=name, lines=count, message=f"Collected {count} lines of {name}, but: {error}")
        note = " (cut to the newest part that fits)" if trimmed else ""
        return AppLogsResult(
            name=name,
            lines=count,
            download_markers=[downloads.marker(offer, "LOGS")],
            message=f"The last {count} lines of {name}{note}. The download link works for 10 minutes.",
        )

    def read_app_logs(self, name: str, lines: int = 200, contains: str | None = None) -> AppLogTextResult:
        """The newest `lines` log lines of an app as text, secrets masked.
        `contains` keeps only matching lines (case-insensitive) among the newest MAX_LOG_LINES."""
        if not 1 <= lines <= MAX_READ_LINES:
            raise ValueError(f"lines must be between 1 and {MAX_READ_LINES}, not {lines}")
        needle = (contains or "").strip().lower()
        container = self._get_container(self._client(), name)
        raw = container.logs(tail=MAX_LOG_LINES if needle else lines, timestamps=True)
        kept = raw.decode("utf-8", errors="replace").splitlines()
        if needle:
            kept = [line for line in kept if needle in line.lower()]
        kept = kept[-lines:]
        if not kept:
            what = f"matching {contains!r}" if needle else "output"
            return AppLogTextResult(
                name=name, lines=0, redactions=0, truncated=False, text="", message=f"{name} has no log {what}."
            )
        text, redactions = redact("\n".join(kept))
        truncated = len(text) > MAX_READ_CHARS
        if truncated:
            text = text[-MAX_READ_CHARS:]
            text = text[text.find("\n") + 1 :]
        count = text.count("\n") + 1 if text else 0
        note = " Older lines were cut to fit the size cap." if truncated else ""
        return AppLogTextResult(
            name=name,
            lines=count,
            redactions=redactions,
            truncated=truncated,
            text=text,
            message=f"{count} log lines of {name}, {redactions} values masked.{note}",
        )

    def list_apps(self) -> AppListResult:
        client = self._client()
        containers = sorted(client.containers.list(all=True), key=lambda container: container.name)
        apps = [
            AppInfo(
                name=container.name,
                status=container.status,
                image=self._image_label(container),
                watched=ServerWatcher.is_active(container.name),
            )
            for container in containers
        ]

        if not apps:
            report = "No apps found on this host."
        else:
            width = max(len(app.name) for app in apps)
            report = "\n".join(
                f"{app.name:<{width}}  {app.status:<10} {'watched' if app.watched else '-':<8} {app.image}"
                for app in apps
            )

        return AppListResult(apps=apps, message=report)


host = DockerHost()
