"""Isolated request worker with bounded lifetime and optional framed reuse."""

from __future__ import annotations

import asyncio
import argparse
import json
import sys
from time import perf_counter, process_time

_WORKER_STARTED = perf_counter()

from pydantic import ValidationError

from src.capabilities.math.contract import MAX_INPUT_BYTES, CalculusRequest, ContinuationRequest, MatrixRequest, SolveRequest, SolveResult
from src.capabilities.math.utils.resources import ResourceGuard


def _calculate(payload: bytes) -> bytes:
    from sympy.core.cache import clear_cache
    from src.capabilities.math.utils.solver import solve_request

    if len(payload) > MAX_INPUT_BYTES:
        result = SolveResult(status="limited", message="Input exceeds 64 KiB.")
    else:
        try:
            envelope = json.loads(payload)
            kind = envelope.get("kind") if isinstance(envelope, dict) else None
            if kind == "continue":
                from src.capabilities.math.utils.continuation import build_continuation
                request = ContinuationRequest.model_validate(envelope)
                request = build_continuation(request.equation, request.data.model_dump())
            elif kind in {"matrix", "calculus"}:
                request = (MatrixRequest if kind == "matrix" else CalculusRequest).model_validate(envelope)
            else:
                request = SolveRequest.model_validate(envelope)
        except ValidationError:
            result = SolveResult(status="invalid", message="Invalid math request.")
        except ValueError as error:
            result = SolveResult(status="invalid", message=str(error)[:512])
        else:
            try:
                if isinstance(request, (MatrixRequest, CalculusRequest)):
                    from src.capabilities.math.utils.advanced import calculate
                    result = calculate(request)
                else:
                    result = solve_request(request)
            finally:
                # Reuse retains initialized libraries, not calculation caches.
                clear_cache()
    clear_cache()
    return result.model_dump_json().encode("utf-8")


def _write(payload: bytes) -> None:
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


async def main(*, framed: bool = False, max_requests: int = 8) -> None:
    guard = ResourceGuard(cpu_seconds=16 * (max_requests if framed else 1))
    try:
        guard.install()
    except OSError:
        await asyncio.to_thread(_write, b'{"ready":false,"error":"Native resource enforcement failed."}\n')
        return
    if framed:
        # Send readiness only after the expensive symbolic engine import.
        await asyncio.to_thread(__import__, "src.capabilities.math.utils.solver")
        ready = {"ready": True, "initialization_ms": (perf_counter() - _WORKER_STARTED) * 1000}
        await asyncio.to_thread(_write, json.dumps(ready).encode("utf-8") + b"\n")
    for _ in range(max_requests if framed else 1):
        if framed:
            payload = await asyncio.to_thread(sys.stdin.buffer.readline, MAX_INPUT_BYTES + 2)
            if not payload:
                return
            payload = payload.removesuffix(b"\n")
        else:
            payload = await asyncio.to_thread(sys.stdin.buffer.read, MAX_INPUT_BYTES + 1)
        cpu_started = process_time()
        encoded = await asyncio.to_thread(_calculate, payload)
        response = json.loads(encoded)
        response["resources"] = guard.snapshot(process_time() - cpu_started)
        encoded = json.dumps(response, separators=(",", ":")).encode("utf-8")
        await asyncio.to_thread(_write, encoded + (b"\n" if framed else b""))
        if len(payload) > MAX_INPUT_BYTES:
            return
        del payload, encoded, response


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Isolated Armory mathematics worker")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--framed", action="store_true")
    modes.add_argument("--once", action="store_true")
    parser.add_argument("--max-requests", type=int, default=8, choices=range(1, 33))
    arguments = parser.parse_args()
    asyncio.run(main(framed=arguments.framed, max_requests=arguments.max_requests))
