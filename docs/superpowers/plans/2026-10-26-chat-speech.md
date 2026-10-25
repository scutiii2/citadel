# Chat Speech Implementation Plan

**Goal:** Implement the approved dictation and read-aloud design across Scribe, Ember and Bard.

**Architecture:** New HTTP routes reuse the existing speech services and identity middleware. Ember proxies authenticated requests; Vue composables own microphone and playback lifecycles.

**Tech Stack:** Starlette, FastAPI, Vue 3, TypeScript, pytest, Vitest, Playwright.

**Spec:** User-supplied approved request; `../specs/2026-10-25-scribe-design.md` and `../specs/2026-10-25-bard-design.md`.

## Constraints

- Preserve existing MCP tools, audio attachments and shared extension configuration.
- English WebM dictation, 150 seconds maximum, 20 MB at Ember; reuse Scribe quotas and cache.
- Explicit voice choice for every read-aloud run; no saved/default choice. Batch cleaned text at 3,500 characters, pipeline one batch ahead, cancel on stop/unmount.
- No secrets inspection, blocking handler IO, new dependencies or motion preferences.
- Test new units, run complete affected suites, typecheck, lint if configured, and browser checks. Commit separately per repository after successful checks.

## Review focus

- Microphone permission resolution after disposal must release tracks without starting recording.
- Late transcription and speech responses must not revive cancelled work or cross account/chat boundaries.
- Synthesis failure while current audio plays must surface without an unhandled rejection.
- Huge sentences and words must remain bounded; markdown code must not be read.
- Every speech route must enforce identity and its permission pair without exposing internal credentials.

## Ordered tasks

- [x] Scribe: tests in `tests/test_app.py`; extend `src/app.py` with raw-body `/api/transcribe`, returning `{text, duration_s}` through upload/transcribe. Run full pytest and commit.
- [x] Ember API: tests in `tests/test_attachments_audio.py`; add `ScribeGateway.transcribe` and `/attachments/dictate`, shared suffix/base64/size checks and metadata-only audit. Run pytest.
- [x] Ember web: client tests and `features/chat/composables/useDictation.test.ts`; implement recorder lifecycle and integrate mic/status/errors in `ChatInput.vue`. Run Vitest.
- [x] Bard: route tests first; add JSON `/api/speak` and installed `/api/voices` in `src/app.py` using existing service/auth. Run full pytest and commit.
- [x] Ember API: gateway and route tests first; implement speak/voices with existing permissions and audit. Run full pytest.
- [x] Ember web: test pure markdown/sentence batching helper, then implement under `utils/`.
- [x] Ember web: test Bard client, playback queue and action button; implement hidden audio, per-run PopupMenu voice choice and cancellable one-ahead synthesis. Integrate in assistant action rows.
- [x] Update service specs, API docs and vault component notes; validate vault.
- [x] Run complete affected suites, typecheck/build and configured lint; verify dev-server browser flows and commit verified work per repo. Report any unavailable real-device/service checks.

## Verification evidence

- Scribe: 38 tests passed; endpoint commit `dda6338`, documentation `922c487`.
- Bard: 94 tests passed; endpoint commit `a8ff45e`, documentation `31fdcd1`.
- Ember API: full suite 1,561 passed (`pytest -q -n 4`), plus two final size/outage cases passed. Proxy commit `1b243457`.
- Ember web: final full suite 2,207 unit tests passed after the mobile popup fix and concurrent independent-prompt changes. TypeScript passes; no separate lint script is configured.
- Chrome: final full browser suite 84 tests passed. Four speech checks passed at 1280/768/375 widths on both built preview and Vite dev servers. Nine focused mobile/speech checks passed after anchoring the expanded tools above the composer.
- Isolated real-service checks used existing cached Whisper `base.en` and installed Piper `en_US-lessac-medium`, scratch storage and explicit synthetic identity/token. No environment file was loaded. Generated microphone speech reached the draft; three real MP3 batches played in order at 16x, with fresh voice selection and working Stop.
- A real 150-second Chrome WebM recording decoded to exactly 150 seconds and Scribe accepted it.
- Light desktop voice menu and dark 375px recording screenshots inspected. Physical microphone/speaker devices were not checked.
- Brain validator: `vault OK`. Updated renamed `Citadel.md` hub, Ember component notes and new Scribe/Bard project notes. No MCP tools or shared-extension policy were changed.
