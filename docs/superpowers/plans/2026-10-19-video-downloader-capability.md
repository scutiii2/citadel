# Video downloader capability implementation plan

**Goal:** Port the approved MediaDownloader MCP brief into native armory tools in an isolated branch from main.
**Spec:** Python/MediaDownloader/docs/codex-armory-capability-brief.md (read-only source).
**Architecture:** Keep the existing policy, guarded yt-dlp adapter, file store, signer and async queue inside capability utils. A process-owned runtime in services runs that queue on a dedicated loop; offloaded tools bridge short operations onto it. Signed files are served on armory's existing listener.
**Tech stack:** Python, FastMCP, Starlette, yt-dlp with guarded curl-cffi, pytest.

## Constraints and review focus
Account UID owns files and jobs; absent identity and exposed tokenless deployments refuse calls. Preserve SSRF fail-closed behavior, quotas, error codes and TTLs. Never use caller-supplied identity. No source project edits, standalone web migration, live website downloads, or vault edits. Capability metadata, README and help must agree. Review cross-account access, disabled routes, forged/expired links, missing FFmpeg, background lifetime and reload safety.

## Tasks
- [x] Port the source regression tests, run them red, then relocate the existing tested modules with import changes only. Add per-owner queue admission tests and caps.
- [x] Add typed contracts, domain facade and four offloaded tools (vid alias, video id). Test identity refusals, untrusted text and immediate job return using a fake extractor.
- [x] Add settings and tracked example config; use the existing config loader. Test config validation and missing FFmpeg at call time. Add the shared background runtime with TTL sweeping and orderly shutdown.
- [x] Install a signed streaming route from command_routes on the existing port. Test valid/range/invalid/expired links, disabled capability and owner isolation; keep the signer independent of requester headers.
- [x] Add README, STATIC-GUIDELINES and help.json. Update read-only declaration tests, check dynamic refresh/load/help and run the complete armory suite. Review branch diff and report unverified live UI behavior and security limitations.


## Execution record

- Worktree: `.worktrees/media-downloader-capability`, branch `codex/media-downloader-capability`, based on main `49efd21c`.
- Catalog check: live localhost:8020 refused connections; documented cache absent. Existing config loader, identity context, offload, untrusted fencing and HTTP/lifespan mechanisms were reused after inspecting source.
- Baseline first failed collection because openpyxl was absent; dependencies were installed in this worktree's isolated venv. No baseline code defect was found.
- Ported policy/store/queue/signer/extractor/service tests failed before the capability existed, then passed after relocation. Native tests caught missing help metadata, changing guard module identities on reload, and dropped MCP error codes; each was corrected and rerun green.
- Ruling: preserve the engine utils subtree across wrapper reloads because shared yt-dlp/curl patches and live jobs must retain the same module identities. Other capabilities keep full-purge behavior. Engine code changes require restart.
- Ruling: preserve signed bearer links on armory's existing listener, with UID ownership required to obtain a link through tools; tighten the standalone privileged MCP lookup to owner-scoped lookup.
- Ruling: retain the existing async queue on one background loop rather than add a JobWatcher for local work already owned by that queue. Jobs do not survive restart; stored files do.
- Independent review found the MCP error-code regression; it was corrected with a thin ToolError conversion and a passing wire-boundary regression. No outstanding actionable findings.
- Complete suite verification and commit details are recorded in the final implementation report. No live website download, browser UI session, deployment-config edit, vault edit, source-project edit or skill change was performed.

Final verification: `pytest -q` from apps/armory: **1165 passed, 2 skipped**, 5 upstream warnings. Static checks found no forbidden AI metadata/client imports or motion settings; runtime folders are ignored.
