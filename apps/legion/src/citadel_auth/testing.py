"""Real isolated test identities; no auth bypass."""

from pathlib import Path

from .keyring import Keyring
from .requester import mint_requester
from .tokens import sign_assertion


async def make_stack(tmp_path, services=("portcullis", "stronghold", "legion", "armory", "treasury")):
    root = Path(tmp_path)
    stack = {name: Keyring(name, root / "trust", root / "identity" / name) for name in services}
    for keyring in stack.values():
        await keyring.ensure_identity()
    return stack


def signed(caller: Keyring, audience: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + sign_assertion(caller, audience)}


def requester_headers(keyring: Keyring, uid: str, username="", email="", aud=None) -> dict[str, str]:
    return {"X-Citadel-Requester": mint_requester(keyring, uid, username, email,
        aud if aud is not None else ["stronghold", "legion", "armory"])}
