"""Notes: read the user's own notes that they allowed agents to read. Read-only."""

from src.services.capability_base import Capability


class Notes(Capability):
    id = "notes"
    label = "Notes"


CAPABILITY = Notes()
