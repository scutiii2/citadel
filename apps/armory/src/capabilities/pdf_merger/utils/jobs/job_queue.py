"""Merge jobs: a global concurrency limit, a timeout, and replayable progress events.

A job's events are kept in a list so a late subscriber (the browser opening
the SSE stream after POST /merge returned) still sees everything. All
publish() calls happen on the event loop thread; worker threads report
progress through loop.call_soon_threadsafe.

Timeouts are cooperative: when the timeout passes, the job's ``cancel``
event is set and the work is awaited until it really stops (Python cannot
kill threads). The semaphore slot is held until then, so timed-out merges
never exceed the concurrency limit and always clean up after themselves.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import threading
import time
from collections.abc import Awaitable, Callable

from src.capabilities.pdf_merger.utils.errors import ErrorCode, MergerError
from src.services.job_events import Job

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int], None]
Work = Callable[[ProgressFn, threading.Event], Awaitable[dict]]


class JobQueue:
    """Runs submitted merge work under a concurrency limit and a timeout."""

    def __init__(self, max_concurrent: int, timeout_seconds: float, clock: Callable[[], float] = time.time) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout = timeout_seconds
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()

    def submit(self, session: str, total_pages: int, work: Work) -> Job:
        job = Job(id="j_" + secrets.token_hex(12), session=session, created_at=self._clock())
        self._jobs[job.id] = job
        task = asyncio.create_task(self._run(job, total_pages, work))
        self._tasks.add(task)  # keep a reference so the task is not garbage-collected
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run(self, job: Job, total: int, work: Work) -> None:
        loop = asyncio.get_running_loop()
        cancel = job.cancel_event

        def progress(done: int) -> None:
            try:
                loop.call_soon_threadsafe(job.publish, {"type": "progress", "done": done, "total": total})
            except RuntimeError:  # the loop closed while a worker thread was still running
                pass

        timeout_event = {
            "type": "error",
            "code": str(ErrorCode.MERGE_TIMEOUT),
            "message": f"The merge took longer than {self._timeout:g} seconds and was stopped. Try fewer pages.",
        }
        job.publish({"type": "queued", "total": total})
        async with self._semaphore:
            if cancel.is_set():  # cancelled while queued: never start the work
                job.publish(timeout_event, final=True)
                return
            job.publish({"type": "progress", "done": 0, "total": total})
            task = asyncio.ensure_future(work(progress, cancel))
            await asyncio.wait({task}, timeout=self._timeout)
            if not task.done():
                cancel.set()
                await asyncio.wait({task})  # hold the slot until the work has really stopped
        try:
            result = task.result()
        except MergerError as error:
            if cancel.is_set():
                job.publish(timeout_event, final=True)
            else:
                job.publish({"type": "error", "code": str(error.code), "message": error.message}, final=True)
        except Exception:
            if cancel.is_set():
                job.publish(timeout_event, final=True)
            else:
                logger.exception("Merge job %s failed", job.id)
                job.publish(
                    {"type": "error", "code": str(ErrorCode.INTERNAL), "message": "The merge failed unexpectedly. Try again."},
                    final=True,
                )
        else:
            job.publish({"type": "done", **result}, final=True)

    def cancel(self, job: Job) -> None:
        job.cancel()

    def get(self, job_id: str, session: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None or job.session != session:
            raise MergerError(ErrorCode.JOB_NOT_FOUND, "This job is not available.")
        return job

    async def wait(self, job: Job) -> dict:
        final: dict = {}
        async for event in job.stream():
            final = event
        return final

    def prune(self, older_than: float) -> int:
        """Forget finished jobs created before ``older_than``."""
        stale = [job_id for job_id, job in self._jobs.items() if job.finished and job.created_at < older_than]
        for job_id in stale:
            del self._jobs[job_id]
        return len(stale)
