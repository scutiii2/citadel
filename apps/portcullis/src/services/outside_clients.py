"""Outside clients: records, keys, budget and audit events. A key is shown once;
only its sha256 hash and 8-character prefix are kept. Events hold no text."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import utcnow
from src.models.outside_client import OutsideClient, OutsideClientEvent

SERVICES = ("legion", "stronghold")
FIELDS = ("name", "services", "ip_allow", "rate_per_minute", "budget_tokens", "budget_days", "enabled")
DEFAULT_BUDGET_TOKENS = 100_000
_NAME = re.compile(r"[A-Za-z0-9 _.\-]{1,60}")


class OutsideClientError(ValueError):
    """A refused change; the message is safe to show."""


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _int_in(value, low: int, high: int, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise OutsideClientError(message)
    return value


class OutsideClients:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _clean(self, field: str, value):
        if field == "name":
            value = value.strip() if isinstance(value, str) else ""
            if not _NAME.fullmatch(value):
                raise OutsideClientError("The name must be 1 to 60 letters, digits, spaces, dashes, underscores or dots.")
            return value
        if field == "services":
            items = list(value or [])
            if not items or len(set(items)) != len(items) or any(s not in SERVICES for s in items):
                raise OutsideClientError(f"Choose one or more distinct services from: {', '.join(SERVICES)}.")
            return items
        if field == "ip_allow":
            items = []
            for entry in value or []:
                try:
                    ipaddress.ip_network(str(entry).strip(), strict=False)
                except ValueError:
                    raise OutsideClientError("Each allowed address must be an IP address or network.") from None
                items.append(str(entry).strip())
            return items
        if field == "rate_per_minute":
            return _int_in(value, 1, 600, "The rate must be 1 to 600 calls a minute.")
        if field == "budget_tokens":
            return _int_in(value, 1, 100_000_000, "The budget must be 1 to 100000000 tokens.")
        if field == "budget_days":
            return _int_in(value, 1, 366, "The budget window must be 1 to 366 days.")
        if not isinstance(value, bool):
            raise OutsideClientError("Enabled must be true or false.")
        return value

    async def _check_name_free(self, name: str, own_id: int | None = None) -> None:
        found = await self.session.scalar(select(OutsideClient.id).where(func.lower(OutsideClient.name) == name.lower()))
        if found is not None and found != own_id:
            raise OutsideClientError("A client with that name already exists.")

    @staticmethod
    def _new_key() -> str:
        return "ock_" + secrets.token_urlsafe(32)

    async def create(self, name, services, rate_per_minute=10, budget_tokens=DEFAULT_BUDGET_TOKENS,
                     budget_days=30, ip_allow=()) -> tuple[OutsideClient, str]:
        values = {f: self._clean(f, v) for f, v in (
            ("name", name), ("services", services), ("rate_per_minute", rate_per_minute),
            ("budget_tokens", budget_tokens), ("budget_days", budget_days), ("ip_allow", ip_allow))}
        await self._check_name_free(values["name"])
        key = self._new_key()
        client = OutsideClient(uid="oc_" + secrets.token_hex(6), key_prefix=key[:8], key_hash=_hash(key), **values)
        self.session.add(client)
        await self.session.flush()
        return client, key

    async def authenticate(self, key: str) -> OutsideClient | None:
        if not key or not key.startswith("ock_"):
            return None
        return await self.session.scalar(select(OutsideClient).where(OutsideClient.key_hash == _hash(key)))

    async def get(self, client_id: int) -> OutsideClient | None:
        return await self.session.get(OutsideClient, client_id)

    async def list(self) -> list[OutsideClient]:
        return list((await self.session.scalars(select(OutsideClient).order_by(OutsideClient.id))).all())

    async def update(self, client_id: int, **changes) -> OutsideClient:
        unknown = sorted(set(changes) - set(FIELDS))
        if unknown:
            raise OutsideClientError(f"Unknown field: {', '.join(unknown)}.")
        client = await self.get(client_id)
        if client is None:
            raise OutsideClientError("No such client.")
        cleaned = {f: self._clean(f, v) for f, v in changes.items()}
        if "name" in cleaned:
            await self._check_name_free(cleaned["name"], client.id)
        for field, value in cleaned.items():
            setattr(client, field, value)
        await self.session.flush()
        return client

    async def rotate_key(self, client_id: int) -> tuple[OutsideClient, str]:
        client = await self.get(client_id)
        if client is None:
            raise OutsideClientError("No such client.")
        key = self._new_key()
        client.key_prefix, client.key_hash = key[:8], _hash(key)
        await self.session.flush()
        return client, key

    async def delete(self, client_id: int) -> bool:
        client = await self.get(client_id)
        if client is None:
            return False
        # Explicit, so events go even where SQLite foreign keys are off.
        await self.session.execute(delete(OutsideClientEvent).where(OutsideClientEvent.client_id == client_id))
        await self.session.delete(client)
        await self.session.flush()
        return True

    async def spent(self, client: OutsideClient, now: datetime | None = None) -> tuple[int, datetime | None]:
        window = timedelta(days=client.budget_days)
        since = (now or utcnow()) - window
        total, oldest = (await self.session.execute(
            select(func.coalesce(func.sum(OutsideClientEvent.tokens), 0), func.min(OutsideClientEvent.at)).where(
                OutsideClientEvent.client_id == client.id, OutsideClientEvent.action == "call",
                OutsideClientEvent.at >= since))).one()
        return (int(total), oldest + window) if oldest is not None else (0, None)

    async def record(self, client: OutsideClient, *, service: str, action: str, reason: str = "",
                     status: int, tokens: int = 0, ip: str = "") -> None:
        self.session.add(OutsideClientEvent(client_id=client.id, service=service, action=action,
                                            reason=reason, status=status, tokens=tokens, ip=ip))
        if action == "call":
            client.last_used_at = utcnow()
        await self.session.flush()

    async def events(self, client_id: int, limit: int = 50, before_id: int | None = None) -> list[OutsideClientEvent]:
        query = select(OutsideClientEvent).where(OutsideClientEvent.client_id == client_id)
        if before_id is not None:
            query = query.where(OutsideClientEvent.id < before_id)
        return list((await self.session.scalars(query.order_by(OutsideClientEvent.id.desc()).limit(limit))).all())
