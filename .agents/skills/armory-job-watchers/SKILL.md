---
name: armory-job-watchers
description: Use when an Armory capability must follow an external job or app in the background (polling, backoff, resume after restart, owner email) by subclassing JobWatcher.
---

# Armory background job watchers

Worked example: `apps/armory/src/capabilities/server_manager/utils/` (`watcher.py` = `JobWatcher` base, `server_watcher.py` = `ServerWatcher`, `notify.py` = owner email). Tool layout: `armory-capability-scaffold`.

The base owns threading, backoff polling, state persistence, cancellation and startup resume. The capability owns what to poll and what to do with the result.

- Define `backoff_schedule` (tiers `[(elapsed_seconds_cutoff, interval_seconds), ...]`, last tier `(float("inf"), s)`), `poll()` returning `(WatcherPhase, detail_dict)`, and `from_record()`. `on_completed()` and `on_state_change()` (runs after the phase is saved, not each poll) do the work.
- Start the watcher from the tool only after the initiating action succeeded (`tool_srv_startApp` calls `watch_app(name)`); record `current_username()` and `current_email()` as owner.
- `YourWatcher.is_active(key)` for live state; `YourWatcher.cancel(state_dir, key)` before a deliberate stop or restart.
- Everything needed to resume goes in the record's `detail`. Call `resume_all(state_dir)` from the capability's `on_startup()`; do not edit `run.py`.
- State files: `{state_dir}/{WatcherClassName}/instances/{key}.json`; `state_dir` is `settings.watchers_dir` (`MCP_WATCHERS_DIR`, default `.data/watchers`). Never in the capability folder.
- Elapsed time counts from the original start, so resume keeps its cadence.
- Email goes through the Email capability (`services/email/delivery.py`, `notification` template). It returns `sent`, `skipped: ...` or `failed: ...`; mail trouble must not stop polling. Document notification rules in the capability README.
- Do not reload a capability while its watchers are in use. A tool-only `listWatchers` belongs to capabilities that have watchers.
