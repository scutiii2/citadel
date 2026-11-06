"""Async application boundary for validated, isolated equation solving."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from collections.abc import Awaitable, Callable

from pydantic import ValidationError

from src.capabilities.math.contract import (
    MAX_BATCH_INPUT_BYTES, MAX_BATCH_OUTPUT_BYTES, BatchProgress, BatchRecord, BatchResult, BatchRow,
    Binding, CalculusRequest, ContinuationRequest, MatrixRequest, RootEquation, SolveRequest, SolveResult, TablePageInfo,
)
from src.capabilities.math.utils.runner import ProcessRunner, runner


class MathDesk:
    """Validate a request and delegate CPU work without blocking Armory's loop."""

    def __init__(self, process_runner: ProcessRunner = runner, *, batch_timeout: float = 60.0) -> None:
        if batch_timeout <= 0:
            raise ValueError("Batch timeout must be positive.")
        self._runner = process_runner
        self._batch_timeout = batch_timeout

    async def solve(self, equation: RootEquation, data: list[Binding]) -> SolveResult:
        try:
            request = SolveRequest(equation=equation, data=data)
        except ValidationError as error:
            reason = error.errors(include_input=False, include_context=False)[0]["msg"]
            return SolveResult(status="invalid", message=f"Invalid math input: {reason}")
        result = await self._runner.run(request)
        # Transport retains raw mappings across wrapper reloads; the fresh
        # contract validates every field, including newly introduced evidence.
        try:
            return SolveResult.model_validate(result)
        except ValidationError:
            return SolveResult(status="error", message="Math worker returned an incompatible result; restart Armory after changing worker contracts.")

    async def continue_from(self, equation, data) -> SolveResult:
        try:
            request = ContinuationRequest(equation=equation, data=data)
        except ValidationError:
            return SolveResult(status="invalid", message="Invalid selected-result continuation input.")
        result = await self._runner.run(request)
        return SolveResult.model_validate(result)

    async def matrix(self, operation, data) -> SolveResult:
        return await self._advanced(MatrixRequest, operation=operation, data=data)

    async def calculus(self, expression, data) -> SolveResult:
        return await self._advanced(CalculusRequest, expression=expression, data=data)

    async def _advanced(self, request_type, **values) -> SolveResult:
        try:
            request = request_type(**values)
        except ValidationError:
            return SolveResult(status="invalid", message="Invalid matrix/calculus input.")
        if len(request.model_dump_json().encode("utf-8")) > 65_536:
            return SolveResult(status="limited", message="Input exceeds 64 KiB.")
        return SolveResult.model_validate(await self._runner.run(request))

    async def table(self, equation, data, *, registry, owner, progress=None) -> BatchResult:
        from src.capabilities.math.utils.table_bridge import TableBridge

        try:
            records, source = await asyncio.to_thread(TableBridge(registry, owner).prepare, data)
            source = TablePageInfo.model_validate(source.model_dump())
        except (ValueError, ValidationError) as error:
            return BatchResult(status="invalid", message=str(error)[:512])
        if not records:
            return BatchResult(status="completed", source=source, message="No rows in requested table page.")
        result = await self.batch(equation, records, progress=progress)
        result.source = source
        return result

    async def batch(self, equation: RootEquation, data: list[Any], *, progress: Callable[[BatchProgress], Awaitable[None]] | None = None) -> BatchResult:
        """Run two bounded producers; validation and failure stay local to each row."""
        if not isinstance(data, list) or not 1 <= len(data) <= 32:
            return BatchResult(status="invalid", message="Batch needs 1–32 records, each with its own data bindings.")
        try:
            payload = json.dumps({"equation": equation, "data": data}, default=lambda value: value.model_dump()).encode("utf-8")
        except (ValueError, TypeError, AttributeError, RecursionError):
            return BatchResult(status="invalid", message="Batch must be a finite JSON tree.")
        if len(payload) > MAX_BATCH_INPUT_BYTES:
            return BatchResult(status="limited", message="Batch input exceeds 256 KiB; split it into smaller batches.")
        try:
            equation = SolveRequest(equation=equation, data=[]).equation
        except ValidationError:
            return BatchResult(status="invalid", message="Invalid shared equation controls.")
        rows: list[BatchRow | None] = [None] * len(data)
        cursor = 0
        output_bytes = 0
        completed = 0
        delivered = 0
        progress_errors = 0
        progress_queue = asyncio.Queue(maxsize=len(data) + 1)

        async def deliver_progress():
            nonlocal delivered
            while (event := await progress_queue.get()) is not None:
                try:
                    async with asyncio.timeout(0.5):
                        await progress(event)
                    delivered += 1
                except Exception:
                    pass  # Transport cannot stall independent calculations.

        progress_task = asyncio.create_task(deliver_progress()) if progress is not None else None

        def identifier(index):
            value = data[index].get("id") if isinstance(data[index], dict) else None
            return value if isinstance(value, str) and len(value) <= 64 else str(index)

        async def produce():
            nonlocal cursor, output_bytes, completed, delivered, progress_errors
            while cursor < len(data):
                index = cursor
                cursor += 1  # No await between taking a record and advancing.
                try:
                    record = BatchRecord.model_validate(data[index])
                except ValidationError as error:
                    reason = error.errors(include_input=False, include_context=False)[0]["msg"]
                    result = SolveResult(status="invalid", message=f"Invalid batch record: {reason[:512]}")
                else:
                    result = await self.solve(equation, record.data)
                row = BatchRow(index=index, id=identifier(index), result=result)
                cost = len(row.model_dump_json().encode("utf-8"))
                # Reserve space for bounded failure messages of all remaining rows.
                if output_bytes + cost > MAX_BATCH_OUTPUT_BYTES - 65_536:
                    row.result = SolveResult(status="limited", message="Batch output budget reached; use fewer records or disable trace.")
                    cost = len(row.model_dump_json().encode("utf-8"))
                output_bytes += cost
                rows[index] = row
                if progress is not None:
                    completed += 1
                    progress_queue.put_nowait(BatchProgress(completed=completed, total=len(data), record=row))

        try:
            async with asyncio.timeout(self._batch_timeout):
                await asyncio.gather(*(produce() for _ in range(min(2, len(data)))))
        except TimeoutError:
            pass  # Runner cancellation reaps active children before gather finishes.
        finally:
            if progress_task is not None:
                progress_queue.put_nowait(None)
                try:
                    async with asyncio.timeout(1.0):
                        await progress_task
                except TimeoutError:
                    pass  # Final results retain rows whose progress was undelivered.
                except asyncio.CancelledError:
                    progress_task.cancel()
                    await asyncio.gather(progress_task, return_exceptions=True)
                    raise
                progress_errors = completed - delivered
        finished = [row if row is not None else BatchRow(index=index, id=identifier(index), result=SolveResult(
            status="timeout", message="Record did not finish before the batch deadline; retry a smaller batch.",
        )) for index, row in enumerate(rows)]
        successes = sum(row.result.status in {"unique", "multiple", "parametric", "approximate", "certified", "inconsistent"} for row in finished)
        return BatchResult(status="completed" if successes == len(finished) else "partial", records=finished,
                           success_count=successes, failure_count=len(finished) - successes,
                           progress_delivered=delivered, progress_errors=progress_errors,
                           message=f"Processed {len(finished)} ordered records with independent results; {len(finished) - successes} need attention.")


desk = MathDesk()
