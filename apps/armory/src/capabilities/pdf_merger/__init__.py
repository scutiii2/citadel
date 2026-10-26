

from src.services.capability_base import Capability


class PdfMerger(Capability):
    id = "pdf"
    label = "PDF Merger"
    # Stores and runtimes here are shared with always-on routes; one identity per process.
    # Editing utils/ needs a restart; tool wrappers still reload.
    process_lifetime_modules = ("utils",)


CAPABILITY = PdfMerger()
