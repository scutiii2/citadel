"""Obsidian vault access through the Local REST API community plugin."""

from src.services import capability_meta

META = capability_meta.register(folder="obsidian", id="obsidian", label="Obsidian")

# Stores and runtimes here are shared with always-on routes; one identity per process.
# Editing utils/ needs a restart; tool wrappers still reload.
PROCESS_LIFETIME_MODULES = ("utils",)
