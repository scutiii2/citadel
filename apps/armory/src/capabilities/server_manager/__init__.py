"""Server manager: start, stop, restart and list the Docker containers on
this host."""

from src.services.capability_base import Capability


class ServerManager(Capability):
    id = "server"
    label = "Server Manager"


CAPABILITY = ServerManager()
