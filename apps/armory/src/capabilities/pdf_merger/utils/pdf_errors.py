"""PDF's names for the shared file errors, so its `except MergerError` clauses keep working."""
from src.services.file_errors import ErrorCode, FileError as MergerError

__all__ = ["ErrorCode", "MergerError"]
