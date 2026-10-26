"""Repo reader: read-only git history, diffs and code search over the workspace projects."""

from src.services.capability_base import Capability


class RepoReader(Capability):
    id = "repo"
    label = "Repo Reader"


CAPABILITY = RepoReader()
