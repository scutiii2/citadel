from src.services import capability_meta

META = capability_meta.register(folder="media_downloader", id="video", label="Media downloader")

# Engine state and process-wide network patches must retain a single identity.
# Updating these modules requires a process restart; wrappers may reload.
PROCESS_LIFETIME_MODULES = ("utils",)
