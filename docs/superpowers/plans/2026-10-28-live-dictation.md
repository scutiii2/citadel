# Live dictation implementation plan

> Agent execution: implement each subsystem with test-first checks, then review the integrated branch before committing.

**Goal:** Display live dictated text without losing the existing draft or recording.

**Architecture:** Scribe owns bounded PCM windowing and LocalAgreement. Ember API authenticates and proxies a same-origin WebSocket. The browser records WebM in parallel and falls back from PCM streaming to rolling HTTP partials to upload on stop.

**Tech stack:** Existing Starlette/FastAPI, faster-whisper, Vue, AudioWorklet, MediaRecorder, WebSocket.

**Spec:** User's pasted live dictation request, 2026-10-28.

## Constraints and review focus

- Never read secrets; preserve unrelated `_TODO.md`; only feature branches, no push or merge.
- PCM is 16 kHz mono signed 16-bit little endian; total audio cap 150 seconds.
- Tokens and identity stay on the server. Authenticate before receiving audio; enforce origin, quotas, frame, idle and concurrency caps.
- Inference and file IO never block the event loop. Repeated partial inference stores no retained audio.
- Record WebM throughout; live failures cannot discard the recording. Late replies after cancellation or scope changes cannot edit a draft.
- Lock draft editing during recording/finalization; cancellation restores the exact base, successful finalization replaces tentative text.
- No new heavy browser dependencies, reduced-motion features, auto-send, or layout overflow at 375px.

## Tasks

- [x] Preserve five waveform files in their own Citadel commit; create matching Scribe branch.
- [x] Scribe: add fake-engine tests for agreement/trimming and authenticated bounded WebSocket partial/final/error flow, watch failures, implement service and socket glue, run full pytest. Then add stateless partial endpoint tests and implementation; update README/AGENTS.
- [x] Ember API: add auth/permission/origin/limit/proxy tests, implement `/api/attachments/dictate/stream` and identity forwarding. Add `/api/attachments/dictate/partial`, action logs and full API suite.
- [x] Browser: test live partial/final, fallback chain, nonoverlapping HTTP, and disposal. Add PCM AudioWorklet resampler, transport lifecycle to composable, stateless partial client method, and Vite WebSocket proxy.
- [x] ChatInput: test locked draft, live replacement, final unlock, cancel/scope restoration; implement callbacks and quiet status with reused tokens. Extend speech e2e for all three transports and cancellation at 1280/768/375; update README.
- [x] Review integration and errors, run full suites plus `vue-tsc -b --noEmit` and Playwright; commit feature changes separately per repo. Report exact results and unverified microphone/Safari/concurrent-user behavior.

## Review and validation

- Review caught initial PCM loss during asynchronous worklet loading and unbounded decoder output. Both fixed with regression tests. Capture readiness is bounded and cancellation invalidates late setup; ffmpeg output and lifetime are bounded and cancelled children are killed and reaped.
- Scribe: `.venv_scribe/Scripts/python.exe -m pytest -q` — 54 passed; three dependency warnings (Pydantic forward reference and deprecated Uvicorn WebSocket APIs).
- Ember API: `.venv_ember_api/Scripts/python.exe -m pytest -n 8` (with persisted verbose/JUnit output) — 1,576 passed, three Starlette deprecation warnings. Fixed disconnect cancellation at the socket boundary with a regression asserting drained relay tasks and released account claims. Synchronized an existing chat-turn test with its fake agent's readiness so it cannot miss its release signal during parallel runs.
- Ember web: `npm test -- --maxWorkers=4` — 185 files, 2,216 tests passed. `npx vue-tsc -b --noEmit` passed.
- Browser: `npm run test:e2e` — 97 passed. Final `npm run test:e2e -- speech.spec.ts` — 13 passed, including capacity fallback and visible status at 1280/768/375px.
- Physical microphone, mobile Safari and multi-user model throughput remain manual verification work. Browser tests use Chrome's fake microphone and mocked transcription transports; Scribe model tests use fake engines.
