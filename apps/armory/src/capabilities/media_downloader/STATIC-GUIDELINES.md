# Media downloader static and runtime storage

Named groups, draft items, package locks and per-item progress are process memory,
like jobs. The existing sweep expires draft/finished history. Restart discards
groups and jobs. Generated package ZIPs use the same stored-file sidecars and
retention as other media; members use temporary `_work/` directories and never
enter the persistent index individually. No new storage location is introduced.

- `.cache/armory/media_downloader/store/`: generated file bytes and UTF-8 JSON StoredFile sidecars under a hash of the account scope. File ids are random; titles never become paths. Unexpired files survive restart; the TTL sweeper deletes expired files and startup removes orphan data and `_work/` scratch directories. Gitignored with `.data/`.
- `.data/armory/media_downloader/logs/` in the Citadel folder: reserved generated diagnostic path (`MCP_MEDIA_LOG_DIR`); no custom logger or handler is installed. Application diagnostics currently go to armory's rotating server log. Untracked, because `.data/` is gitignored.
- No `.cache/` or `static/` reference data is created. yt-dlp disk caching is disabled; gallery-dl's anonymous discovery cache is in memory, and its user config/cookies are never loaded. Photo scratch files and numbered ZIPs use the same `_work/` cleanup as video. Queue/progress and sweep timers are process memory, not files; they are regenerated on restart.
- `apps/armory/configs/config_media_downloader.json`: tracked, holds the hand-maintained caps/TTLs; `configs/README.md` explains it. Environment values and signing material are supplied by armory's deployment environment; no credential files are created here.
