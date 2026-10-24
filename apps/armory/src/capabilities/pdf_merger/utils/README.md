# PDF merger internals

Ported from the standalone PDFMerger engine. These modules contain no server, REST routes, MCP decorators, environment loading, or application startup.

- `converters/`: validates PDFs and supported raster images and converts images to PDF pages.
- `engine/`: expands page selections and assembles ordered PDF output with rotations, metadata and bookmarks.
- `store/`: owner-scoped files and quotas (on `src/services/session_file_store.py`), safe names and MIME sniffing. Signed links and the expiry sweeper are shared in `src/services/link_signing.py` and `file_sweeper.py`.
- `jobs/`: bounded merge concurrency and progress events on the shared `src/services/job_queue.py` and `job_events.py`.
- `service.py`: shared facade composing the engine, store, queue and signer.
- `models.py`, `errors.py`, `config.py`: engine models, typed errors and immutable settings.

The capability runtime supplies paths and settings. State belongs under `specifics/pdf_merger/.data/`; scratch files are removed after each merge and expired files by the sweeper. Caller scope always equals its owner session, including callers authenticated with the internal token. Only a successfully verified signed download link permits lookup without owner scope.
