"""Server manager: start, stop, restart and list the Docker containers on
this host."""

from src.services.capability_base import Capability


class ServerManager(Capability):
    id = "server"
    label = "Server Manager"
    # ServerWatcher threads are shared with run.py's startup resume; one class identity per process.
    # Editing utils/ needs a restart; tool wrappers still reload.
    process_lifetime_modules = ("utils",)


CAPABILITY = ServerManager()
