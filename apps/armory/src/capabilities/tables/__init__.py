"""Tables: read-only questions about a CSV or XLSX file the user attached in chat."""

from src.services.capability_base import Capability


class Tables(Capability):
    id = "data"
    label = "Data Tables"
    # Stores and runtimes here are shared with always-on routes; one identity per process.
    # Editing utils/ needs a restart; tool wrappers still reload.
    process_lifetime_modules = ("utils",)


CAPABILITY = Tables()
