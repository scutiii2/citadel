"""The port plan: named port ranges and which server reserves which port.

A server always starts on its reserved port. When that port is busy it moves
within its own range, never onto a port another server has reserved, and it
never falls back to a fixed default such as 8000."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FALLBACK_RANGE = "Unassigned"
MIN_PORT, MAX_PORT = 1, 65535

PortBusy = Callable[[int], bool]


class PortPlanError(ValueError):
    """The change or request cannot be honored; the message is safe to show."""


@dataclass(frozen=True)
class PortRange:
    """A block of ports, both ends included."""

    name: str
    start: int
    end: int

    def __contains__(self, port: object) -> bool:
        return isinstance(port, int) and self.start <= port <= self.end

    def overlaps(self, other: PortRange) -> bool:
        return self.start <= other.end and other.start <= self.end

    @property
    def size(self) -> int:
        return self.end - self.start + 1


def _checked_range(name: str, start: object, end: object) -> PortRange:
    name = " ".join(str(name).split())
    if not name:
        raise PortPlanError("A range needs a name.")
    for value in (start, end):
        if isinstance(value, bool) or not isinstance(value, int) or not MIN_PORT <= value <= MAX_PORT:
            raise PortPlanError(f"Ports run from {MIN_PORT} to {MAX_PORT}.")
    if start > end:  # type: ignore[operator]
        raise PortPlanError("A range cannot end before it starts.")
    return PortRange(name, start, end)  # type: ignore[arg-type]


class PortPlan:
    def __init__(
        self, ranges: Iterable[PortRange] = (), reservations: dict[str, int] | None = None,
        fallback: str = FALLBACK_RANGE,
    ) -> None:
        self._ranges: list[PortRange] = []
        self._reservations: dict[str, int] = {}
        self.fallback = fallback
        for port_range in ranges:
            self.add_range(port_range.name, port_range.start, port_range.end)
        for key, port in (reservations or {}).items():
            self.reserve(key, port)

    # ---- reading -------------------------------------------------------------

    @property
    def ranges(self) -> list[PortRange]:
        return list(self._ranges)

    @property
    def reservations(self) -> dict[str, int]:
        return dict(self._reservations)

    def range_named(self, name: str) -> PortRange | None:
        return next((r for r in self._ranges if r.name == name), None)

    def range_of(self, port: int) -> PortRange | None:
        return next((r for r in self._ranges if port in r), None)

    def port_for(self, key: str) -> int | None:
        return self._reservations.get(key)

    def owner_of(self, port: int) -> str | None:
        return next((key for key, reserved in self._reservations.items() if reserved == port), None)

    def keys_in(self, port_range: PortRange) -> list[str]:
        """The servers reserved inside the range, by port."""
        return [key for key, port in sorted(self._reservations.items(), key=lambda item: item[1]) if port in port_range]

    def conflict(self, key: str, port: int) -> str | None:
        """Why `key` may not use `port`: another server has reserved it."""
        owner = self.owner_of(port)
        if owner is not None and owner != key:
            return f"Port {port} is reserved for {owner}."
        return None

    # ---- editing -------------------------------------------------------------

    def add_range(self, name: str, start: int, end: int) -> PortRange:
        new = _checked_range(name, start, end)
        if self.range_named(new.name) is not None:
            raise PortPlanError(f"There is already a range called {new.name}.")
        self._refuse_overlap(new, ignore=None)
        self._ranges.append(new)
        self._ranges.sort(key=lambda r: r.start)
        return new

    def update_range(self, old_name: str, name: str, start: int, end: int) -> PortRange:
        """Renames or resizes a range. Every reservation must stay inside it."""
        old = self.range_named(old_name)
        if old is None:
            raise PortPlanError(f"There is no range called {old_name}.")
        new = _checked_range(name, start, end)
        if new.name != old.name and self.range_named(new.name) is not None:
            raise PortPlanError(f"There is already a range called {new.name}.")
        self._refuse_overlap(new, ignore=old)
        stranded = [key for key in self.keys_in(old) if self._reservations[key] not in new]
        if stranded:
            raise PortPlanError(f"{', '.join(stranded)} would fall outside {new.name}. Release or move them first.")
        self._ranges[self._ranges.index(old)] = new
        self._ranges.sort(key=lambda r: r.start)
        if self.fallback == old.name:
            self.fallback = new.name
        return new

    def remove_range(self, name: str) -> None:
        port_range = self.range_named(name)
        if port_range is None:
            raise PortPlanError(f"There is no range called {name}.")
        if name == self.fallback:
            raise PortPlanError(f"{name} is where servers without a reservation go. Keep it.")
        held = self.keys_in(port_range)
        if held:
            raise PortPlanError(f"{', '.join(held)} still reserve ports in {name}. Release them first.")
        self._ranges.remove(port_range)

    def reserve(self, key: str, port: int) -> None:
        """Reserves `port` for `key`, replacing its earlier reservation."""
        if isinstance(port, bool) or not isinstance(port, int) or self.range_of(port) is None:
            raise PortPlanError(f"Port {port} is not inside any range.")
        owner = self.owner_of(port)
        if owner is not None and owner != key:
            raise PortPlanError(f"Port {port} is already reserved for {owner}.")
        self._reservations[key] = port

    def release(self, key: str) -> None:
        self._reservations.pop(key, None)

    def _refuse_overlap(self, new: PortRange, ignore: PortRange | None) -> None:
        for existing in self._ranges:
            if existing is not ignore and existing.overlaps(new):
                raise PortPlanError(f"{new.name} overlaps {existing.name} ({existing.start}-{existing.end}).")

    # ---- choosing ports ------------------------------------------------------

    def _first_free(self, key: str, port_range: PortRange, busy: PortBusy, after: int | None = None) -> int | None:
        for port in range(port_range.start, port_range.end + 1):
            if after is not None and port <= after:
                continue
            owner = self.owner_of(port)
            if (owner is None or owner == key) and not busy(port):
                return port
        return None

    def _search_range(self, key: str, near: int | None) -> PortRange:
        for port in (near, self._reservations.get(key)):
            if port is not None and (found := self.range_of(port)) is not None:
                return found
        fallback = self.range_named(self.fallback)
        if fallback is None:
            raise PortPlanError(f"The {self.fallback} range is missing.")
        return fallback

    def free_port(self, key: str, desired: int, busy: PortBusy) -> int:
        """The port to start `key` on: `desired` when it is free and not reserved
        for another server, else the first free port of the range it sits in
        (the key's own range, then the fallback range, when it sits in none)."""
        if self.conflict(key, desired) is None and not busy(desired):
            return desired
        port_range = self._search_range(key, desired)
        # Prefer the next port up from the one asked for, then wrap to the start of the range.
        found = self._first_free(key, port_range, busy, after=desired)
        if found is None:
            found = self._first_free(key, port_range, busy)
        if found is None:
            raise PortPlanError(f"No free port in {port_range.name} ({port_range.start}-{port_range.end}).")
        return found

    def allocate(self, key: str, busy: PortBusy, preferred: int | None = None) -> int:
        """Reserves a port for `key` and returns it: `preferred` when it is inside a
        range and unreserved, else the first free port of the fallback range."""
        if preferred is not None and self.range_of(preferred) is not None and self.owner_of(preferred) is None:
            self.reserve(key, preferred)
            return preferred
        fallback = self.range_named(self.fallback)
        if fallback is None:
            raise PortPlanError(f"The {self.fallback} range is missing.")
        found = self._first_free(key, fallback, busy)
        if found is None:
            raise PortPlanError(f"No free port in {fallback.name} ({fallback.start}-{fallback.end}).")
        self.reserve(key, found)
        return found

    # ---- file form -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "fallback": self.fallback,
            "ranges": [{"name": r.name, "start": r.start, "end": r.end} for r in self._ranges],
            "reservations": dict(sorted(self._reservations.items(), key=lambda item: item[1])),
        }

    @classmethod
    def from_dict(cls, data: object) -> PortPlan:
        if not isinstance(data, dict) or not isinstance(data.get("ranges"), list):
            raise PortPlanError("The port plan file is not in the expected shape.")
        plan = cls(fallback=str(data.get("fallback") or FALLBACK_RANGE))
        for entry in data["ranges"]:
            if not isinstance(entry, dict):
                raise PortPlanError("A range in the port plan file is not an object.")
            plan.add_range(entry.get("name", ""), entry.get("start"), entry.get("end"))
        reservations = data.get("reservations", {})
        if not isinstance(reservations, dict):
            raise PortPlanError("The reservations in the port plan file are not an object.")
        for key, port in reservations.items():
            plan.reserve(str(key), port)
        return plan


def default_plan() -> PortPlan:
    """The plan a new data folder starts with: today's ports, grouped into blocks."""
    return PortPlan(
        [
            PortRange("Tools", 8010, 8029),
            PortRange("Ember", 8030, 8039),
            PortRange("Apps", 8040, 8099),
            PortRange(FALLBACK_RANGE, 8100, 8199),
            PortRange("Web", 5170, 5179),
            PortRange("Agents", 9100, 9199),
        ],
        {
            "mcp_server": 8010, "catalog_service": 8020,
            "ember_api": 8030,
            "pdf_merger": 8040, "video_downloader": 8050, "ascension": 8060, "chess": 8070, "db_gateway": 8071,
            "ember_web": 5173, "pdf_merger_web": 5174, "video_downloader_web": 5175, "ember_admin": 5176,
            "ai_agent": 9100,
        },
    )


def load_plan(path: Path) -> PortPlan:
    """The saved plan, or the default one when the file is missing or unusable."""
    try:
        return PortPlan.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, PortPlanError):
        return default_plan()


def save_plan(plan: PortPlan, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")


def assign_ports(plan: PortPlan, templates: Iterable[Any], busy: PortBusy, preferred: Callable[[Any], int]) -> bool:
    """Gives every server a reserved port, sets its `default_port` to it and returns
    whether the plan changed. A server with no reservation keeps the port its own
    run.bat names when that sits inside a free part of a range, else it gets the
    next free port of the fallback range. An unplanned server never lands on 8000."""
    changed = False
    for template in templates:
        port = plan.port_for(template.key)
        if port is None:
            port = plan.allocate(template.key, busy, preferred(template))
            changed = True
        template.default_port = port
    return changed
