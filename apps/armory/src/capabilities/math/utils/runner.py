"""Bounded reusable processes, framed JSON, phase timing, and reliable reaping."""

from __future__ import annotations

import asyncio
import json
import sys
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from src.capabilities.math.contract import MAX_OUTPUT_BYTES
from src.capabilities.math.utils.metrics import MetricLedger

if TYPE_CHECKING:
    from src.capabilities.math.contract import SolveRequest


@dataclass
class Admission:
    semaphore: asyncio.Semaphore
    loop_ref: weakref.ReferenceType
    pending: int = 0
    closed: bool = False
    idle: list[Worker] = field(default_factory=list)
    workers: set[Worker] = field(default_factory=set)
    spawns: dict[asyncio.Task, asyncio.Event] = field(default_factory=dict)
    background: set[asyncio.Task] = field(default_factory=set)


@dataclass(eq=False)
class Worker:
    process: asyncio.subprocess.Process
    requests: int = 0
    initialization_ms: float = 0.0
    idle_task: asyncio.Task | None = None
    read_task: asyncio.Task | None = None
    closing_task: asyncio.Task | None = None


class OutputLimitError(ValueError):
    """Worker exceeded the maximum response size."""


class ProcessRunner:
    """Reuse bounded workers; failed/cancelled workers exit before releasing slots."""

    def __init__(self, *, command: tuple[str, ...] | None = None, max_workers: int = 2,
                 max_pending: int = 16, timeout: float = 15.0, reuse_workers: bool | None = None,
                 max_requests: int = 8, idle_timeout: float = 30.0) -> None:
        if max_workers < 1 or max_pending < max_workers or timeout <= 0 or not 1 <= max_requests <= 32 or idle_timeout <= 0:
            raise ValueError("Worker limits must be positive, pending capacity must cover workers, and request budget must be 1–32.")
        self._reuse = command is None if reuse_workers is None else reuse_workers
        self._command = command or (
            sys.executable, "-m", "src.capabilities.math.utils.worker",
            "--framed" if self._reuse else "--once", "--max-requests", str(max_requests),
        )
        self._max_workers = max_workers
        self._max_pending = max_pending
        self._timeout = timeout
        self._max_requests = max_requests
        self._idle_timeout = idle_timeout
        self._loops: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
        self._metrics: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    def snapshot(self) -> dict:
        ledger = self._metrics.get(asyncio.get_running_loop())
        return (ledger or MetricLedger()).snapshot()

    async def run(self, request: SolveRequest) -> dict:
        """Transport raw mappings so wrapper reloads cannot discard new fields."""
        loop = asyncio.get_running_loop()
        started = loop.time()
        ledger = self._metrics.get(loop)
        if ledger is None:
            ledger = MetricLedger()
            self._metrics[loop] = ledger
        admission = self._loops.get(loop)
        if admission is None:
            admission = Admission(asyncio.Semaphore(self._max_workers), weakref.ref(loop))
            self._loops[loop] = admission
        if admission.closed:
            result = self._failure("error", "Math workers are shutting down.")
            ledger.record(result, 0, (loop.time() - started) * 1000)
            return result
        # Admission is atomic within the event loop: no await before increment.
        if admission.pending >= self._max_pending:
            result = self._failure("limited", "Math worker queue is full; try again later.")
            ledger.record(result, 0, (loop.time() - started) * 1000)
            return result
        admission.pending += 1
        queue_ms = 0.0
        acquired = False
        try:
            async with asyncio.timeout(self._timeout):
                async with admission.semaphore:
                    acquired = True
                    queue_ms = (loop.time() - started) * 1000
                    if admission.closed:
                        result = self._failure("error", "Math workers are shutting down.")
                    else:
                        result = await self._execute(admission, request.model_dump_json().encode("utf-8"))
        except TimeoutError:
            if not acquired:
                queue_ms = (loop.time() - started) * 1000
            result = self._failure("timeout", "Calculation exceeded its queue/execution deadline; worker stopped.")
        except asyncio.CancelledError:
            if not acquired:
                queue_ms = (loop.time() - started) * 1000
            ledger.record({"status": "cancelled"}, queue_ms, (loop.time() - started) * 1000)
            raise
        except OutputLimitError:
            result = self._failure("limited", "Math worker output exceeds 256 KiB.")
        except (OSError, ValueError, RuntimeError, asyncio.IncompleteReadError):
            result = self._failure("error", "Math worker could not complete the calculation.")
        finally:
            admission.pending -= 1
            self._drop_empty(admission)
        result.setdefault("timings", {}).update(queue_ms=queue_ms, total_ms=(loop.time() - started) * 1000)
        ledger.record(result, queue_ms, result["timings"]["total_ms"])
        return result

    @staticmethod
    def _failure(status: str, message: str) -> dict:
        return {"status": status, "message": message, "completeness": "unknown", "diagnostics": [{
            "code": f"worker_{status}", "detail": message,
            "suggestion": "Retry a smaller calculation or narrow the search; a worker failure does not establish mathematical inconsistency.",
        }]}

    async def _spawn(self, admission: Admission) -> Worker:
        if admission.closed:
            raise RuntimeError("Worker pool is closing.")
        spawning = asyncio.create_task(asyncio.create_subprocess_exec(
            *self._command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, cwd=Path(__file__).resolve().parents[4],
            limit=MAX_OUTPUT_BYTES + 1,
        ))
        finished = asyncio.Event()
        admission.spawns[spawning] = finished
        worker = None
        try:
            process = await asyncio.shield(spawning)
            worker = Worker(process)
            admission.workers.add(worker)
            if admission.closed:
                await self._retire(admission, worker)
                raise RuntimeError("Worker pool is closing.")
            return worker
        finally:
            try:
                if worker is None:
                    await self._cleanup(self._reap_spawn(spawning))
            finally:
                admission.spawns.pop(spawning, None)
                finished.set()

    @staticmethod
    async def _reap_spawn(spawning: asyncio.Task) -> None:
        try:
            process = await spawning
        except OSError:
            return
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        if process.stdin is not None:
            process.stdin.close()
        if process.stdout is not None:
            while await process.stdout.read(65_536):
                pass
        await process.wait()

    @staticmethod
    async def _cleanup(awaitable):
        """Wait through repeated cancellation, then propagate it after cleanup."""
        task = asyncio.ensure_future(awaitable)
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        result = task.result()
        if cancelled:
            raise asyncio.CancelledError
        return result

    async def _read_frame(self, worker: Worker) -> dict:
        assert worker.process.stdout is not None
        worker.read_task = asyncio.create_task(worker.process.stdout.readuntil(b"\n"))
        try:
            output = await worker.read_task
        except asyncio.LimitOverrunError as error:
            raise OutputLimitError from error
        if len(output) - 1 > MAX_OUTPUT_BYTES:
            raise OutputLimitError
        result = json.loads(output)
        if not isinstance(result, dict):
            raise ValueError("Expected a JSON object.")
        return result

    async def _checkout(self, admission: Admission) -> tuple[Worker, bool, float]:
        while admission.idle:
            worker = admission.idle.pop()
            if worker.idle_task is not None:
                worker.idle_task.cancel()
            if worker.closing_task is not None or worker.process.returncode is not None:
                await self._retire(admission, worker)
                continue
            return worker, True, 0.0
        started = asyncio.get_running_loop().time()
        worker = await self._spawn(admission)
        try:
            if self._reuse:
                ready = await self._read_frame(worker)
                if ready.get("ready") is not True:
                    raise ValueError("Worker did not send readiness handshake.")
                worker.initialization_ms = float(ready.get("initialization_ms", 0.0))
            return worker, False, (asyncio.get_running_loop().time() - started) * 1000
        except BaseException:
            await self._retire(admission, worker)
            raise

    async def _execute(self, admission: Admission, payload: bytes) -> dict:
        worker, reused, startup_ms = await self._checkout(admission)
        process = worker.process
        completed = False
        started = asyncio.get_running_loop().time()
        try:
            assert process.stdin is not None and process.stdout is not None
            try:
                process.stdin.write(payload + (b"\n" if self._reuse else b""))
                await process.stdin.drain()
                if not self._reuse:
                    process.stdin.close()
                    await process.stdin.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
            if self._reuse:
                result = await self._read_frame(worker)
            else:
                output = bytearray()
                while True:
                    worker.read_task = asyncio.create_task(process.stdout.read(min(65_536, MAX_OUTPUT_BYTES + 1 - len(output))))
                    chunk = await worker.read_task
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > MAX_OUTPUT_BYTES:
                        raise OutputLimitError
                await process.wait()
                if process.returncode:
                    return self._failure("error", "Math worker exited before completing the calculation.")
                result = json.loads(output)
            if not isinstance(result, dict) or not isinstance(result.get("status"), str) or not isinstance(result.get("message"), str):
                raise ValueError("Worker returned an invalid result envelope.")
            worker.requests += 1
            result["execution"] = {"worker_reused": reused, "worker_request": worker.requests}
            result.setdefault("timings", {}).update(
                startup_ms=startup_ms, initialization_ms=0.0 if reused else worker.initialization_ms,
                request_ms=(asyncio.get_running_loop().time() - started) * 1000,
            )
            completed = result["status"] not in {"limited", "error", "timeout"}
            return result
        finally:
            if completed and self._reuse and worker.requests < self._max_requests and not admission.closed:
                admission.idle.append(worker)
                worker.idle_task = asyncio.create_task(self._expire(admission, worker))
                admission.background.add(worker.idle_task)
                worker.idle_task.add_done_callback(admission.background.discard)
            else:
                await self._retire(admission, worker)

    async def _expire(self, admission: Admission, worker: Worker) -> None:
        try:
            await asyncio.sleep(self._idle_timeout)
        finally:
            # Checkout removes it before cancelling the timer; loop shutdown
            # cancels timers while idle workers still belong to the pool.
            if worker in admission.idle:
                await self._retire(admission, worker)

    async def _retire(self, admission: Admission, worker: Worker) -> None:
        if worker.closing_task is None:
            worker.closing_task = asyncio.create_task(self._dispose(admission, worker))
        await self._cleanup(worker.closing_task)

    async def _dispose(self, admission: Admission, worker: Worker) -> None:
        process = worker.process
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        if worker.read_task is not None and not worker.read_task.done():
            worker.read_task.cancel()
            await asyncio.gather(worker.read_task, return_exceptions=True)
        if process.stdin is not None:
            process.stdin.close()
        if process.stdout is not None:
            while await process.stdout.read(65_536):
                pass  # Drain bounded pipe buffers after killing, avoiding wait deadlock.
        await process.wait()
        admission.workers.discard(worker)
        if worker in admission.idle:
            admission.idle.remove(worker)
        self._drop_empty(admission)

    def _drop_empty(self, admission: Admission) -> None:
        loop = admission.loop_ref()
        if not admission.pending and not admission.workers and not admission.spawns and self._loops.get(loop) is admission:
            self._loops.pop(loop, None)

    async def close(self) -> None:
        """Reap this loop's active/idle workers during server lifespan shutdown."""
        loop = asyncio.get_running_loop()
        admission = self._loops.get(loop)
        if admission is None:
            return
        admission.closed = True

        async def close_state():
            # Creation owners adopt or reap their children before signalling;
            # shutdown must not race them by reading the same pipe itself.
            await asyncio.gather(*(finished.wait() for finished in list(admission.spawns.values())))
            for task in list(admission.background):
                task.cancel()
            await asyncio.gather(*(self._retire(admission, worker) for worker in list(admission.workers)))
            await asyncio.gather(*list(admission.background), return_exceptions=True)
            self._drop_empty(admission)

        await self._cleanup(close_state())


runner = ProcessRunner()
