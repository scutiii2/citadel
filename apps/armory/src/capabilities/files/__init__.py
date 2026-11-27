"""Every file the signed-in account has uploaded or made."""

from src.services.capability_base import Capability


class Files(Capability):
    id = "files"
    label = "Files"


CAPABILITY = Files()
