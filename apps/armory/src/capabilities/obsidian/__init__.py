"""Obsidian vault access through the Local REST API community plugin."""

from src.services import capability_meta

META = capability_meta.register(folder="obsidian", id="obsidian", label="Obsidian")
