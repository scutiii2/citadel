# Media download internals

`packages.py` owns account-scoped draft groups and locks membership synchronously
when the existing queue accepts a package job. It reuses `service.py` extraction
and policy checks, runs members sequentially, records individual failures and
stores one numbered ZIP through the existing quota/TTL store. Draft/finished
group history is bounded and swept; only completed ZIP files survive restart.

Ported from the standalone MediaDownloader service: URL policy and thread-scoped socket/curl guards; blocking yt-dlp adapter; limits and presets; scoped file store and names; async queue. The store, job queue and event log build on `src/services/session_file_store.py`, `job_queue.py` and `job_events.py`; link signing and the TTL sweeper are `src/services/link_signing.py` and `file_sweeper.py`. `service.py` composes them. `extractor/media.py` dispatches video/music to yt-dlp and raster images/social photo posts to `extractor/photos.py`. Photo discovery uses gallery-dl, while guarded requests downloads bytes with combined size limits, cancellation, image validation and numbered ZIP output for carousels. No gallery download jobs, user config or imported cookies are used. `config.py` contains the original service dataclasses, populated by armory's process runtime. Source tests are retained under `tests/media_downloader/`, with import paths changed. Network fixture tests only serve synthetic bytes on loopback with an explicit test guard; production guards always require public addresses.
