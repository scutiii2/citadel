"""Notes: read the user's own notes that they allowed agents to read. Read-only."""

from src.services import capability_meta

META = capability_meta.register(folder="notes", id="notes", label="Notes")
