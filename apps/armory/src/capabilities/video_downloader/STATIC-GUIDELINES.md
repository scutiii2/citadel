# Media downloader static and runtime storage

Named groups, draft items, package locks and per-item progress are process memory,
like jobs. The existing sweep expires draft/finished history. Restart discards
groups and jobs. Generated package ZIPs use the same stored-file sidecars and
retention as other media; members use temporary `_work/` directories and never
enter the persistent index individually. No new storage location is introduced.

- `apps/armory/specifics/video_downloader/.data/store/`: generated file bytes and UTF-8 JSON StoredFile sidecars under a hash of the account scope. File ids are random; titles never become paths. Unexpired files survive restart; the TTL sweeper deletes expired files and startup removes orphan data and `_work/` scratch directories. Gitignored by the existing `specifics/*/.data/` rule.
- `apps/armory/specifics/video_downloader/.logs/`: reserved generated diagnostic path (`MCP_VIDEO_LOG_DIR`); no custom logger or handler is installed. Application diagnostics currently go to armory's rotating server log. Gitignored by the existing `.logs/` rule.
- No `.cache/` or `static/` reference data is created. yt-dlp disk caching is disabled; gallery-dl's anonymous discovery cache is in memory, and its user config/cookies are never loaded. Photo scratch files and numbered ZIPs use the same `_work/` cleanup as video. Queue/progress and sweep timers are process memory, not files; they are regenerated on restart.
- `apps/armory/specifics/video_downloader/configs/`: tracked `config_video_downloader.json.example` documents hand-maintained caps/TTLs. The actual deployment JSON is materialized by the shared config loader and is gitignored by the existing `config_*.json` rule. Environment values and signing material are supplied by armory's deployment environment; no credential files are created here.
