

from src.services.capability_base import Capability


class MediaDownloader(Capability):
    id = "media"
    label = "Media downloader"
    # Engine state and process-wide network patches must retain a single identity.
    # Updating these modules requires a process restart; wrappers may reload.
    process_lifetime_modules = ("utils",)


CAPABILITY = MediaDownloader()
