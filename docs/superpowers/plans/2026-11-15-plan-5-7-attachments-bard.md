# Plan 5.7: Attachments and Bard speech move to Stronghold

Branch: `refactor/stronghold-attachments`.

## What moved

1. Stronghold `src/attachments/`: reading text from an attached file (`extraction.py`, with its zip-bomb, page and row limits), and the routes `POST /attachments/text|table|pdf|audio|document|dictate|dictate/partial`. PDFs and tables go to Armory (`/upload/pdf`, `/upload/table`), attached audio and dictation to Scribe, documents to Reader. Stronghold logs `attachments.table|pdf|audio|document|dictate` (never the words).
2. Stronghold `src/bard/`: `POST /bard/speak` and `GET /bard/voices`. Logs `bard.speak` without the spoken text.
3. Stronghold `src/attachments/services.py` holds the clients for Scribe, Reader, Bard and Armory's uploads, with the same error mapping as before (the service's own 400/413 message is kept, anything else is a 502).
4. Portcullis keeps the login and permission checks (`files.upload`; `tools.execute` plus `files.download` for Bard) and passes the JSON body on (`pass_on`).
5. Portcullis keeps what must stream: `GET /api/attachments/files/{id}/content` (Armory, with Range), `GET /api/bard/audio/{id}` (Bard, with Range) and the `WS /api/attachments/dictate/stream` relay to Scribe. These need Portcullis's own Scribe/Bard settings.
6. Removed from Portcullis: `services/reader.py`, `services/text_extraction.py`, the Scribe upload/transcribe methods, the Bard speak/voices methods, `reader_url`, the Reader token, and the `pypdf`, `python-docx` and `openpyxl` dependencies. Their tests moved to Stronghold (`test_attachments.py`, `test_bard.py`, `test_extraction_limits.py`); Portcullis tests now check the pass-through.

## You must do

1. Put `BARD_TOKEN`, `SCRIBE_TOKEN` and `READER_TOKEN` in `apps/stronghold/.env` (the same tokens that are in Portcullis's `.env` today). Without them Stronghold's calls to those services answer 401 and the browser sees 502.
2. Outside Docker, set `BARD_URL`, `SCRIBE_URL`, `READER_URL` for Stronghold if the defaults (ports 29400, 29401, 29402) are wrong. Docker already sets them.
3. Portcullis still needs `BARD_TOKEN` and `SCRIBE_TOKEN` (audio streaming and dictation socket). `READER_TOKEN` is no longer read there.

## Accepted behavior changes

1. Attached files, dictation and speech need Stronghold running; when it is down the browser sees 502 `Stronghold is unavailable`.
2. A table the Armory upload cannot reach now says `armory is unreachable` (was `mcp_server is unreachable`).
3. Every file travels one more hop (Portcullis to Stronghold), as base64 JSON, up to the same size caps.
4. The Portcullis `reader_url` setting is gone; an old `config_app.json` that still has it is simply ignored.

## Execution notes (2026-11-15)

- Stronghold suite: 439 passed. Portcullis: full-suite result is in the commit message.
- Not run: Docker builds; a real file through Scribe, Reader, Bard and Armory; the attach, dictate and speak buttons in a browser.
