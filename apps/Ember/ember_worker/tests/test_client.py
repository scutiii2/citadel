from __future__ import annotations

import asyncio
import json

import pytest
from websockets.asyncio.server import serve

from src.client import WorkerClient
from src.config import WorkerConfig
from src.events import Failed, Finished, TextDelta
from src.providers.base import Provider


class ScriptedProvider(Provider):
    name = "claude"

    def __init__(self, script, plan="Max") -> None:
        self.script, self.plan = script, plan
        self.requests, self.cancelled = [], []

    async def detect_plan(self):
        return self.plan

    async def is_logged_in(self):
        return True

    async def run_turn(self, request, gate):
        self.requests.append(request)
        for item in self.script:
            if callable(item):
                await item(gate)
            else:
                yield item

    async def cancel(self, turn_id):
        self.cancelled.append(turn_id)


def make_config(port: int, heartbeat: float = 20, overrides=None) -> WorkerConfig:
    return WorkerConfig(f"http://127.0.0.1:{port}", heartbeat, overrides or {}, {"claude": "ft_test"})


TURN = {"type": "turn", "turn_id": "t1", "group_id": 1, "folder": ".", "mode": "ask", "prompt": "hi", "history": []}


async def with_server(handler, scenario, **server_kwargs):
    async with serve(handler, "127.0.0.1", 0, **server_kwargs) as server:
        port = server.sockets[0].getsockname()[1]
        return await scenario(port)


async def run_client_until(client: WorkerClient, done: asyncio.Event, timeout: float = 5.0) -> None:
    task = asyncio.create_task(client.run())
    try:
        await asyncio.wait_for(done.wait(), timeout)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_hello_ready_then_a_turn_is_run_and_answered() -> None:
    seen, done = [], asyncio.Event()

    async def handler(ws):
        seen.append(("auth", ws.request.headers.get("Authorization")))
        seen.append(json.loads(await ws.recv()))  # hello
        await ws.send(json.dumps({"type": "ready", "worker_id": 7}))
        await ws.send(json.dumps(TURN))
        async for raw in ws:
            frame = json.loads(raw)
            seen.append(frame)
            if frame["type"] == "turn_done":
                done.set()

    async def scenario(port):
        provider = ScriptedProvider([TextDelta("Hi"), Finished("Hi there")])
        await run_client_until(WorkerClient(provider, make_config(port), "ft_test"), done)
        return provider

    provider = asyncio.run(with_server(handler, scenario))

    assert seen[0] == ("auth", "Bearer ft_test")
    assert seen[1]["type"] == "hello" and seen[1]["plan"] == "Max" and seen[1]["version"]
    assert [f["type"] for f in seen[2:]] == ["delta", "turn_done"]
    assert provider.requests[0].prompt == "hi" and provider.requests[0].turn_id == "t1"


def test_the_plan_override_beats_detection() -> None:
    seen, done = [], asyncio.Event()

    async def handler(ws):
        seen.append(json.loads(await ws.recv()))
        done.set()
        await ws.wait_closed()

    async def scenario(port):
        client = WorkerClient(ScriptedProvider([], plan="Pro"), make_config(port, overrides={"claude": "Max 20x"}), "ft_test")
        await run_client_until(client, done)

    asyncio.run(with_server(handler, scenario))

    assert seen[0]["plan"] == "Max 20x"


def test_heartbeats_are_sent_while_connected() -> None:
    beats, done = [], asyncio.Event()

    async def handler(ws):
        await ws.recv()
        await ws.send(json.dumps({"type": "ready", "worker_id": 1}))
        async for raw in ws:
            if json.loads(raw)["type"] == "heartbeat":
                beats.append(1)
                if len(beats) >= 2:
                    done.set()

    async def scenario(port):
        await run_client_until(WorkerClient(ScriptedProvider([]), make_config(port, heartbeat=0.05), "ft_test"), done)

    asyncio.run(with_server(handler, scenario))

    assert len(beats) >= 2


def test_permission_questions_travel_both_ways() -> None:
    seen, done = [], asyncio.Event()

    async def ask(gate):
        seen.append(("answer", await gate.ask("Bash", "ls")))

    async def handler(ws):
        await ws.recv()
        await ws.send(json.dumps({"type": "ready", "worker_id": 1}))
        await ws.send(json.dumps(TURN))
        async for raw in ws:
            frame = json.loads(raw)
            if frame["type"] == "permission_request":
                await ws.send(json.dumps({"type": "permission_reply", "request_id": frame["request_id"], "allow": True}))
            if frame["type"] == "turn_done":
                done.set()

    async def scenario(port):
        provider = ScriptedProvider([ask, Finished("ok")])
        await run_client_until(WorkerClient(provider, make_config(port), "ft_test"), done)

    asyncio.run(with_server(handler, scenario))

    assert seen == [("answer", True)]


def test_a_cancel_frame_reaches_the_provider() -> None:
    cancelled, done = [], asyncio.Event()

    async def hang(gate):
        await asyncio.sleep(30)

    async def handler(ws):
        await ws.recv()
        await ws.send(json.dumps({"type": "ready", "worker_id": 1}))
        await ws.send(json.dumps(TURN))
        await asyncio.sleep(0.1)
        await ws.send(json.dumps({"type": "cancel", "turn_id": "t1"}))
        async for raw in ws:
            if json.loads(raw)["type"] == "turn_error":
                done.set()

    async def scenario(port):
        provider = ScriptedProvider([hang])
        client = WorkerClient(provider, make_config(port), "ft_test")
        client._cancel_grace = 0.05
        await run_client_until(client, done)
        return provider

    provider = asyncio.run(with_server(handler, scenario))

    assert provider.cancelled == ["t1"]


def test_it_reconnects_after_the_server_drops_it() -> None:
    connections, done = [], asyncio.Event()

    async def handler(ws):
        connections.append(1)
        await ws.recv()
        await ws.send(json.dumps({"type": "ready", "worker_id": 1}))
        if len(connections) == 1:
            await ws.close(code=1011)
        else:
            done.set()
            await ws.wait_closed()

    async def scenario(port):
        client = WorkerClient(ScriptedProvider([]), make_config(port), "ft_test", backoff_start=0.01, backoff_max=0.02)
        await run_client_until(client, done)

    asyncio.run(with_server(handler, scenario))

    assert len(connections) == 2


def test_a_running_turn_is_failed_when_the_connection_drops() -> None:
    async def hang(gate):
        await asyncio.sleep(30)

    async def go():
        provider = ScriptedProvider([hang])
        dropped = asyncio.Event()
        ended = []

        async def handler(ws):
            await ws.recv()
            await ws.send(json.dumps({"type": "ready", "worker_id": 1}))
            await ws.send(json.dumps(TURN))
            await asyncio.sleep(0.1)
            await ws.close(code=1011)
            dropped.set()

        async def scenario(port):
            client = WorkerClient(provider, make_config(port), "ft_test", backoff_start=5, backoff_max=5)
            task = asyncio.create_task(client.run())
            await asyncio.wait_for(dropped.wait(), 5)
            await asyncio.sleep(0.2)  # the client notices and shuts the runner down
            ended.append(task.done())
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        await with_server(handler, scenario)
        return ended

    assert asyncio.run(go()) == [False]  # still running (waiting to reconnect), not crashed


def test_a_rejected_token_ends_the_client_without_retrying() -> None:
    connections = []

    async def handler(ws):
        connections.append(1)
        await ws.recv()
        await ws.close(code=4401)

    async def scenario(port):
        client = WorkerClient(ScriptedProvider([]), make_config(port), "ft_bad", backoff_start=0.01)
        await asyncio.wait_for(client.run(), 5)  # returns instead of looping

    asyncio.run(with_server(handler, scenario))

    assert connections == [1]


def test_a_handshake_refusal_also_means_the_token_was_rejected() -> None:
    from http import HTTPStatus

    connections = []

    async def handler(ws):
        connections.append(1)

    def refuse(connection, request):
        return connection.respond(HTTPStatus.FORBIDDEN, "no\n")

    async def scenario(port):
        client = WorkerClient(ScriptedProvider([]), make_config(port), "ft_bad", backoff_start=0.01)
        await asyncio.wait_for(client.run(), 5)

    asyncio.run(with_server(handler, scenario, process_request=refuse))

    assert connections == []


def test_it_keeps_retrying_while_the_server_is_unreachable() -> None:
    async def go():
        client = WorkerClient(ScriptedProvider([]), make_config(1), "ft_test", backoff_start=0.01, backoff_max=0.02)
        task = asyncio.create_task(client.run())
        await asyncio.sleep(0.2)
        alive = not task.done()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return alive

    assert asyncio.run(go()) is True
