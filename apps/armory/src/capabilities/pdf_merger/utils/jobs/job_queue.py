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

import logging
import threading
import time
from collections.abc import Awaitable, Callable

from src.capabilities.pdf_merger.utils.errors import ErrorCode, MergerError
from src.services.job_events import Job
from src.services.job_queue import JobQueueBase

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int], None]
Work = Callable[[ProgressFn, threading.Event], Awaitable[dict]]


class JobQueue(JobQueueBase):
    """Runs submitted merge work under a concurrency limit and a timeout."""

    def __init__(self, max_concurrent: int, timeout_seconds: float, clock: Callable[[], float] = time.time) -> None:
        super().__init__(max_concurrent, timeout_seconds, clock)

    def submit(self, session: str, total_pages: int, work: Work) -> Job:
        return self._start(session, lambda job: self._run(job, total_pages, work))

    async def _run(self, job: Job, total: int, work: Work) -> None:
        publish = self._publisher(job)
        cancel = job.cancel_event

        def progress(done: int) -> None:
            publish({"type": "progress", "done": done, "total": total})

        timeout_event = {
            "type": "error",
            "code": str(ErrorCode.MERGE_TIMEOUT),
            "message": f"The merge took longer than {self._timeout:g} seconds and was stopped. Try fewer pages.",
        }
        job.publish({"type": "queued", "total": total})

        def start() -> Awaitable[dict]:
            job.publish({"type": "progress", "done": 0, "total": total})
            return work(progress, cancel)

        task, _ = await self._in_slot(job, start)
        if task is None:  # cancelled while queued
            job.publish(timeout_event, final=True)
            return
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

    def get(self, job_id: str, session: str) -> Job:
        job = self._find(job_id, session)
        if job is None:
            raise MergerError(ErrorCode.JOB_NOT_FOUND, "This job is not available.")
        return job
