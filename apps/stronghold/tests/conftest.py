"""Shared fixtures. Tests never read the real .env or the shared token file."""

import os

os.environ["INTERNAL_TOKEN_FILE"] = ""
