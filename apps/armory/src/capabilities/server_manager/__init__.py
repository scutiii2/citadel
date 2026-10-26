"""Server manager: start, stop, restart and list the Docker containers on
this host."""

from src.services.capability_base import Capability


class ServerManager(Capability):
    id = "server"
    label = "Server Manager"
    # ServerWatcher threads are shared with its on_startup resume; one class identity per process.
    # Editing utils/ needs a restart; tool wrappers still reload.
    process_lifetime_modules = ("utils",)

    def on_startup(self) -> None:
        """Restart the app watchers that were running when the server last stopped."""
        from src.capabilities.server_manager.utils.server_watcher import ServerWatcher
        from src.config import settings

        ServerWatcher.resume_all(settings.watchers_dir)


CAPABILITY = ServerManager()
