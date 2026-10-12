"""Ability trees: the nodes one Ascended can learn, as a validated graph.

A node is an ability or a passive. Roots are the Ascended's starting kit: always
learned, no cost. Every other node needs its prerequisites, a level and essence.
Pure: no database, files or HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from src.ascension.models import AbilitySpec, PassiveSpec


class TreeError(ValueError):
    """The tree is not a valid graph."""


def passive_root_id(ascended_id: str) -> str:
    """The id of the root node that holds an Ascended's own passive."""
    return f"{ascended_id}_passive"


@dataclass(frozen=True)
class NodeCost:
    tier: str  # the essence tier spent
    amount: int


@dataclass(frozen=True)
class TreeNode:
    id: str
    kind: str  # "ability" or "passive"
    name: str
    x: float
    y: float
    requires: tuple[str, ...] = ()
    unlock_level: int = 1
    cost: NodeCost | None = None  # None for roots
    root: bool = False
    ability: AbilitySpec | None = None
    passive: PassiveSpec | None = None

    def to_public(self) -> dict[str, Any]:
        """The node as the API shows it (public data, no player state)."""
        shown: dict[str, Any] = {
            "id": self.id, "kind": self.kind, "name": self.name, "x": self.x, "y": self.y,
            "requires": list(self.requires), "unlock_level": self.unlock_level, "root": self.root,
            "cost": {"tier": self.cost.tier, "amount": self.cost.amount} if self.cost else None,
        }
        if self.ability is not None:
            a = self.ability
            shown.update(category=a.category, percentage=a.percentage, cooldown=a.cooldown, stat=a.stat, duration=a.duration,
                         effects=[e.to_dict() for e in a.effects])
        if self.passive is not None:
            shown["passive"] = self.passive.to_dict()
        return shown


class AbilityTree:
    def __init__(self, nodes: Iterable[TreeNode]) -> None:
        self.nodes: tuple[TreeNode, ...] = tuple(nodes)
        self._by_id = {n.id: n for n in self.nodes}
        self._validate()

    def node(self, node_id: str) -> TreeNode | None:
        return self._by_id.get(node_id)

    @property
    def roots(self) -> tuple[TreeNode, ...]:
        return tuple(n for n in self.nodes if n.root)

    def _validate(self) -> None:
        if len(self._by_id) != len(self.nodes):
            raise TreeError("node ids must be unique")
        if not self.roots:
            raise TreeError("a tree needs at least one root node")
        points: set[tuple[float, float]] = set()
        for node in self.nodes:
            for required in node.requires:
                if required not in self._by_id:
                    raise TreeError(f"node {node.id!r} requires unknown node {required!r}")
            if node.root and node.requires:
                raise TreeError(f"root node {node.id!r} cannot have requirements")
            if not node.root and not node.requires:
                raise TreeError(f"node {node.id!r} is unreachable: it has no requirements and is not a root")
            if (node.x, node.y) in points:
                raise TreeError(f"node {node.id!r} sits on the same point as another node")
            points.add((node.x, node.y))
        reached = {n.id for n in self.roots}
        grew = True
        while grew:
            grew = False
            for node in self.nodes:
                if node.id not in reached and all(r in reached for r in node.requires):
                    reached.add(node.id)
                    grew = True
        stranded = [n.id for n in self.nodes if n.id not in reached]
        if stranded:
            raise TreeError(f"nodes unreachable from a root (or in a cycle): {', '.join(stranded)}")
