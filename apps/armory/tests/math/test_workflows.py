"""Progress and table workflows share existing ownership and batch guarantees."""

from __future__ import annotations

import asyncio

import pytest

from src.capabilities.math.domain import MathDesk
from src.capabilities.math.utils.runner import ProcessRunner
from src.capabilities.tables.utils.tables import ParsedTable, TableRegistry


@pytest.mark.asyncio
async def test_progress_delivers_complete_indexed_rows_before_batch_returns():
    runner = ProcessRunner()
    events = []
    async def progress(event):
        events.append(event)
        await asyncio.sleep(0)
    try:
        result = await MathDesk(runner).batch("y=2*x", [{"data": [{"type": "constant", "name": "x", "value": n}]} for n in (2, 3)], progress=progress)
        assert [event.completed for event in events] == [1, 2]
        assert {event.record.index for event in events} == {0, 1}
        assert all(event.record.result.solutions for event in events)
        assert result.progress_delivered == 2
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_broken_progress_consumer_does_not_abort_calculations():
    runner = ProcessRunner()
    async def progress(event):
        raise RuntimeError("consumer disconnected")
    try:
        result = await MathDesk(runner).batch("x=2", [{"data": []}], progress=progress)
        assert result.success_count == 1
        assert result.progress_errors == 1
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_stalled_progress_does_not_consume_calculation_deadline():
    class ImmediateRunner:
        async def run(self, request):
            await asyncio.sleep(0)
            return {"status": "unique", "completeness": "complete", "message": "Complete."}
    async def progress(event):
        await asyncio.Event().wait()
    result = await MathDesk(ImmediateRunner(), batch_timeout=0.05).batch("x=1", [{"data": []} for _ in range(5)], progress=progress)
    assert result.success_count == 5 and result.failure_count == 0
    assert result.progress_errors == 5


def table(registry, owner="alice"):
    return registry.add(owner, "values.csv", ParsedTable(columns=["Input", "Time"], kinds=["number", "number"],
                        data=[[1.23456789012345, 2, None], [1, 2, 3]], row_count=3, sheet=None, notes=[]), size_bytes=100)


@pytest.mark.asyncio
async def test_table_pages_preserve_cell_precision_and_ownership():
    registry = TableRegistry()
    attached = table(registry)
    runner = ProcessRunner()
    try:
        desk = MathDesk(runner)
        result = await desk.table("y=x", {"table_id": attached.id, "columns": {"x": "Input"}, "limit": 2}, registry=registry, owner="alice")
        assert result.records[0].result.solutions[0].values["y"].exact == "24691357802469/20000000000000"
        assert result.source.next_offset == 2
        assert result.source.total_rows == 3
        denied = await desk.table("y=x", {"table_id": attached.id, "columns": {"x": "Input"}}, registry=registry, owner="bob")
        unknown = await desk.table("y=x", {"table_id": "unknown", "columns": {"x": "Input"}}, registry=registry, owner="alice")
        assert denied.status == unknown.status == "invalid"
        assert denied.message == unknown.message
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_missing_cell_stays_local_and_empty_page_starts_no_work():
    registry = TableRegistry()
    attached = table(registry)
    runner = ProcessRunner()
    try:
        desk = MathDesk(runner)
        result = await desk.table("y=x", {"table_id": attached.id, "columns": {"x": "Input"}, "offset": 2}, registry=registry, owner="alice")
        assert result.records[0].result.status == "invalid"
        assert result.source.next_offset is None
        empty = await desk.table("y=x", {"table_id": attached.id, "columns": {"x": "Input"}, "offset": 10}, registry=registry, owner="alice")
        assert empty.status == "completed"
        assert empty.records == []
    finally:
        await runner.close()
