# Video download internals

Ported from the standalone VideoDownloader service: URL policy and thread-scoped socket/curl guards; blocking yt-dlp adapter; limits and presets; scoped file store, names and signing; async queue and TTL sweeper. `service.py` composes them. `config.py` contains the original service dataclasses, populated by armory's process runtime. Source tests are retained under `tests/video_downloader/`, with import paths changed. Network fixture tests only serve synthetic bytes on loopback with an explicit test guard; production guards always require public addresses.
