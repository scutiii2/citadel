"""Support tickets: report bugs and failures, suggest features, follow your own tickets."""
from src.services import capability_meta

META = capability_meta.register(folder="tickets", id="ticket", label="Tickets")

# Stores and runtimes here are shared with always-on routes; one identity per process.
# Editing utils/ needs a restart; tool wrappers still reload.
PROCESS_LIFETIME_MODULES = ("utils",)
