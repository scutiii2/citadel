"""Download jobs: concurrency limit, bounded wait queue, timeout, replayable events.
Cancels are cooperative and the semaphore slot is held until the work really stops."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Awaitable, Callable

from src.capabilities.media_downloader.utils.errors import DownloaderError, ErrorCode
from src.services.job_events import Job
from src.services.job_queue import JobQueueBase

logger = logging.getLogger(__name__)

Emit = Callable[[dict], None]
Work = Callable[[Emit, threading.Event], Awaitable[dict]]


def _error(code: ErrorCode, message: str) -> dict:
    return {"type": "error", "code": str(code), "message": message}


class JobQueue(JobQueueBase):
    """Runs submitted downloads under a concurrency limit, a queue bound and a timeout."""

    def __init__(
        self, max_concurrent: int, max_queued: int, timeout_seconds: float, clock: Callable[[], float] = time.time
    ) -> None:
        super().__init__(max_concurrent, timeout_seconds, clock)
        self._capacity = max_concurrent + max_queued
        self._max_per_caller: int | None = None

    def submit(self, session: str, work: Work) -> Job:
        if sum(1 for job in self._jobs.values() if not job.finished) >= self._capacity:
            raise DownloaderError(ErrorCode.QUEUE_FULL, "Too many downloads are running. Try again in a minute.")
        if self._max_per_caller is not None and sum(1 for job in self._jobs.values() if not job.finished and job.session == session) >= self._max_per_caller:
            raise DownloaderError(ErrorCode.QUEUE_FULL, "Your download queue is full. Wait for one of your jobs to finish.")
        return self._start(session, lambda job: self._run(job, work))

    async def _run(self, job: Job, work: Work) -> None:
        emit = self._publisher(job)
        cancel = job.cancel_event
        cancelled = _error(ErrorCode.CANCELLED, "The download was cancelled.")
        timed_out = _error(
            ErrorCode.TIMEOUT, f"The download took longer than {self._timeout / 60:g} minutes and was stopped."
        )
        job.publish({"type": "queued"})
        task, timeout_hit = await self._in_slot(job, lambda: work(emit, cancel))
        if task is None:  # cancelled while queued
            job.publish(cancelled, final=True)
            return
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

    def cancel_all(self) -> int:
        """Ask every unfinished job to stop (used at shutdown). Returns how many were asked."""
        unfinished = [job for job in self._jobs.values() if not job.finished]
        for job in unfinished:
            job.cancel()
        return len(unfinished)

    def get(self, job_id: str, session: str | None) -> Job:
        job = self._find(job_id, session)
        if job is None:
            raise DownloaderError(ErrorCode.JOB_NOT_FOUND, "That job is not available.")
        return job
