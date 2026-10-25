"""Tables: read-only questions about a CSV or XLSX file the user attached in chat."""

from src.services import capability_meta

META = capability_meta.register(folder="tables", id="data", label="Data Tables")

# Stores and runtimes here are shared with always-on routes; one identity per process.
# Editing utils/ needs a restart; tool wrappers still reload.
PROCESS_LIFETIME_MODULES = ("utils",)
