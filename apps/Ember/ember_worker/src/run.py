"""ember_worker entry point: ``python -m src.run`` (see run.bat).

  run.bat pair <ember_url> <token> --provider claude [--plan "Max"]
  run.bat status
  run.bat                       connect every paired worker
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from src.client import WorkerClient
from src.config import PROVIDERS, ROOT, ConfigError, load_config, save_pairing
from src.providers.base import Provider
from src.providers.registry import build_provider

ProviderFactory = Callable[[str], Provider]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ember-worker", description="Connect your Claude Code and Codex CLIs to Ember's Forge page.")
    commands = parser.add_subparsers(dest="command")
    pair = commands.add_parser("pair", help="pair this computer's CLI with a worker made on the Forge page")
    pair.add_argument("url", help="the address of ember_api, for example https://ember.example.com")
    pair.add_argument("token", help="the one-time token the Forge page showed")
    pair.add_argument("--provider", required=True, choices=PROVIDERS)
    pair.add_argument("--plan", help="your subscription plan, when the CLI cannot report it")
    commands.add_parser("status", help="show the login, plan and pairing of each CLI")
    commands.add_parser("run", help="connect every paired worker (the default)")
    return parser


def _error(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


async def _pair(args: argparse.Namespace, root: Path, make_provider: ProviderFactory) -> int:
    provider = make_provider(args.provider)
    if not await provider.is_logged_in():
        return _error(
            f"The {args.provider} CLI is not logged in on this computer. Log in with it first, then pair again."
        )
    save_pairing(root, args.provider, args.url, args.token, args.plan)
    plan = args.plan or await provider.detect_plan()
    print(f"Paired the {args.provider} worker with {args.url.rstrip('/')}.")
    if plan:
        print(f"Plan: {plan}")
    else:
        print('The CLI did not report a plan. If Ember refuses the worker, pair again with --plan "<your plan>".')
    print("Start it with: run.bat")
    return 0


async def _status(root: Path, make_provider: ProviderFactory) -> int:
    config = load_config(root)
    print(f"Ember: {config.url}")
    for name in PROVIDERS:
        provider = make_provider(name)
        logged_in = await provider.is_logged_in()
        plan = config.plan_override.get(name) or (await provider.detect_plan() if logged_in else None) or "unknown"
        print(f"{name}")
        print(f"  logged in: {'yes' if logged_in else 'no'}")
        print(f"  plan: {plan}")
        print(f"  paired: {'yes' if config.tokens.get(name) else 'no'}")
    return 0


async def _run(root: Path, make_provider: ProviderFactory) -> int:
    config = load_config(root)
    paired = config.paired_providers()
    if not paired:
        return _error("No worker is paired yet. Make one on the Forge page, then run: run.bat pair <url> <token> --provider claude")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    clients = [WorkerClient(make_provider(name), config, config.tokens[name]) for name in paired]
    print(f"Connecting {', '.join(paired)} to {config.url} ... (Ctrl+C to stop)")
    await asyncio.gather(*(client.run() for client in clients))
    return 0


def main(
    argv: Sequence[str] | None = None, *, root: Path = ROOT, provider_factory: ProviderFactory = build_provider
) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"
    try:
        if command == "pair":
            return asyncio.run(_pair(args, root, provider_factory))
        if command == "status":
            return asyncio.run(_status(root, provider_factory))
        return asyncio.run(_run(root, provider_factory))
    except ConfigError as error:
        return _error(str(error))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
