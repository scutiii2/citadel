"""Download jobs: a concurrency limit, a bounded wait queue, a timeout, replayable events.

A job's events are kept in a list so a late subscriber (the browser opening the
SSE stream after POST /downloads returned) still sees everything. publish() runs
on the event loop thread; worker threads report through ``emit``, which hops to
the loop with call_soon_threadsafe.

Timeouts and cancels are cooperative: the job's ``cancel`` event is set and the
work is awaited until it really stops (Python cannot kill threads). The
semaphore slot is held until then, so stopped downloads never exceed the
concurrency limit and always clean up after themselves.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import threading
import time
from collections.abc import Awaitable, Callable

from src.capabilities.media_downloader.utils.errors import DownloaderError, ErrorCode
from src.services.job_events import Job

logger = logging.getLogger(__name__)

Emit = Callable[[dict], None]
Work = Callable[[Emit, threading.Event], Awaitable[dict]]


def _error(code: ErrorCode, message: str) -> dict:
    return {"type": "error", "code": str(code), "message": message}


class JobQueue:
    """Runs submitted downloads under a concurrency limit, a queue bound and a timeout."""

    def __init__(
        self, max_concurrent: int, max_queued: int, timeout_seconds: float, clock: Callable[[], float] = time.time
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._capacity = max_concurrent + max_queued
        self._max_per_caller: int | None = None
        self._timeout = timeout_seconds
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()

    def submit(self, session: str, work: Work) -> Job:
        if sum(1 for job in self._jobs.values() if not job.finished) >= self._capacity:
            raise DownloaderError(ErrorCode.QUEUE_FULL, "Too many downloads are running. Try again in a minute.")
        if self._max_per_caller is not None and sum(1 for job in self._jobs.values() if not job.finished and job.session == session) >= self._max_per_caller:
            raise DownloaderError(ErrorCode.QUEUE_FULL, "Your download queue is full. Wait for one of your jobs to finish.")
        job = Job(id="j_" + secrets.token_hex(12), session=session, created_at=self._clock())
        self._jobs[job.id] = job
        task = asyncio.create_task(self._run(job, work))
        self._tasks.add(task)  # keep a reference so the task is not garbage-collected
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run(self, job: Job, work: Work) -> None:
        loop = asyncio.get_running_loop()
        cancel = job.cancel_event

        def emit(event: dict) -> None:
            try:
                loop.call_soon_threadsafe(job.publish, event)
            except RuntimeError:  # the loop closed while a worker thread was still running
                pass

        cancelled = _error(ErrorCode.CANCELLED, "The download was cancelled.")
        timed_out = _error(
            ErrorCode.TIMEOUT, f"The download took longer than {self._timeout / 60:g} minutes and was stopped."
        )
        job.publish({"type": "queued"})
        timeout_hit = False
        async with self._semaphore:
            if cancel.is_set():  # cancelled while queued: never start the work
                job.publish(cancelled, final=True)
                return
            task = asyncio.ensure_future(work(emit, cancel))
            await asyncio.wait({task}, timeout=self._timeout)
            if not task.done():
                timeout_hit = True
                cancel.set()
                await asyncio.wait({task})  # hold the slot until the work has really stopped
        try:
            result = task.result()
        except DownloaderError as error:
            job.publish(timed_out if timeout_hit else _error(error.code, error.message), final=True)
        except Exception:
            if timeout_hit:
                job.publish(timed_out, final=True)
            elif cancel.is_set():
                job.publish(cancelled, final=True)
            else:
                logger.exception("Download job %s failed", job.id)
                job.publish(_error(ErrorCode.INTERNAL, "The download failed unexpectedly. Try again."), final=True)
        else:
            job.publish({"type": "done", **result}, final=True)

    def cancel(self, job: Job) -> None:
        job.cancel()

    def cancel_all(self) -> int:
        """Ask every unfinished job to stop (used at shutdown). Returns how many were asked."""
        unfinished = [job for job in self._jobs.values() if not job.finished]
        for job in unfinished:
            job.cancel()
        return len(unfinished)

    def get(self, job_id: str, session: str | None) -> Job:
        job = self._jobs.get(job_id)
        if job is None or (session is not None and job.session != session):
            raise DownloaderError(ErrorCode.JOB_NOT_FOUND, "That job is not available.")
        return job

    async def wait(self, job: Job) -> dict:
        """The job's final event."""
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
