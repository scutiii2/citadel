"""The slot-holding core shared by the pdf_merger and media_downloader job queues.

A queue runs submitted work under a concurrency limit and a cooperative timeout (Python cannot
kill threads): when the timeout passes the job's ``cancel`` event is set and the work is awaited
until it really stops, so the slot is never released early. Each capability owns what its jobs
publish (events, error codes, messages); this base owns the bookkeeping.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Awaitable, Callable

from src.services.job_events import Job


class JobQueueBase:
    def __init__(self, max_concurrent: int, timeout_seconds: float, clock: Callable[[], float] = time.time) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._timeout = timeout_seconds
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()

    def _start(self, session: str, run: Callable[[Job], Awaitable[None]]) -> Job:
        """Register a job and run ``run(job)`` as a task."""
        job = Job(id="j_" + secrets.token_hex(12), session=session, created_at=self._clock())
        self._jobs[job.id] = job
        task = asyncio.create_task(run(job))
        self._tasks.add(task)  # keep a reference so the task is not garbage-collected
        task.add_done_callback(self._tasks.discard)
        return job

    @staticmethod
    def _publisher(job: Job) -> Callable[[dict], None]:
        """A thread-safe ``publish`` for worker threads; call it from the event loop."""
        loop = asyncio.get_running_loop()

        def publish(event: dict) -> None:
            try:
                loop.call_soon_threadsafe(job.publish, event)
            except RuntimeError:  # the loop closed while a worker thread was still running
                pass

        return publish

    async def _in_slot(self, job: Job, make_work: Callable[[], Awaitable[dict]]) -> tuple[asyncio.Future | None, bool]:
        """Wait for a slot, run ``make_work()`` in it and hold the slot until it stops.

        Returns ``(None, False)`` when the job was cancelled while queued (the work never
        starts), else ``(task, timed_out)``.
        """
        async with self._semaphore:
            if job.cancel_event.is_set():
                return None, False
            task = asyncio.ensure_future(make_work())
            await asyncio.wait({task}, timeout=self._timeout)
            timed_out = not task.done()
            if timed_out:
                job.cancel_event.set()
                await asyncio.wait({task})  # hold the slot until the work has really stopped
            return task, timed_out

    def _find(self, job_id: str, session: str | None) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None or (session is not None and job.session != session):
            return None
        return job

    def cancel(self, job: Job) -> None:
        job.cancel()

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
