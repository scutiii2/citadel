"""Ability trees in play: what an Ascended can learn, what it learned, what it equips."""

from __future__ import annotations

from typing import Any

from src.ascension.catalog import Catalog
from src.ascension.errors import InsufficientEssence, InvalidRequest, NotFound, UpgradeNotReady, WrongPhase
from src.ascension.idempotency import IdempotentWriter
from src.ascension.models import Loadout, PassiveSpec
from src.ascension.records import AscendedRecord
from src.ascension.repository import AscendedRepository, AscendedTransaction
from src.ascension.tree import TreeNode, passive_root_id

ABILITY_SLOTS = ("a1", "a2", "a3")
PASSIVE_SLOT = "p1"
NO_PASSIVE = PassiveSpec("none", {})


class TreeService:
    def __init__(self, repository: AscendedRepository, writer: IdempotentWriter, catalog: Catalog) -> None:
        self._repository, self._writer, self._catalog = repository, writer, catalog

    # -- helpers -------------------------------------------------------------------

    async def _owned(self, tx: AscendedTransaction, owner: str, ascended_id: str) -> AscendedRecord:
        record = await tx.get_ascended(owner, ascended_id) if self._catalog.has_ascended(ascended_id) else None
        if record is None:
            raise NotFound("you do not own that Ascended")
        return record

    def _learned(self, ascended_id: str, stored: set[str]) -> set[str]:
        return {n.id for n in self._catalog.ascended(ascended_id).tree.roots} | stored

    def _default_slots(self, ascended_id: str) -> dict[str, str]:
        spec = self._catalog.ascended(ascended_id)
        slots = {slot: a.id for slot, a in zip(ABILITY_SLOTS, spec.abilities)}
        slots[PASSIVE_SLOT] = passive_root_id(ascended_id)
        return slots

    def _slots(self, ascended_id: str, stored: dict[str, str]) -> dict[str, str]:
        return stored if stored else self._default_slots(ascended_id)

    def _state(self, node: TreeNode, record: AscendedRecord, learned: set[str], essences: dict[str, int], tree) -> tuple[str, str | None]:
        if node.id in learned:
            return "learned", None
        for required in node.requires:
            if required not in learned:
                return "locked", f"needs {tree.node(required).name}"
        if record.level < node.unlock_level:
            return "locked", f"needs level {node.unlock_level}"
        have = essences.get(node.cost.tier, 0)
        if have < node.cost.amount:
            return "locked", f"needs {node.cost.amount} {node.cost.tier} essence"
        return "learnable", None

    @staticmethod
    async def _reject_if_fighting(tx: AscendedTransaction, owner: str, ascended_id: str) -> None:
        battle = await tx.active_battle(owner)
        if battle is not None and battle.setup.player.ascended_id == ascended_id:
            raise WrongPhase("that Ascended is fighting in the active battle")

    # -- reads ---------------------------------------------------------------------

    async def view(self, owner: str, ascended_id: str) -> dict[str, Any]:
        async with self._repository.transaction() as tx:
            record = await self._owned(tx, owner, ascended_id)
            learned = self._learned(ascended_id, await tx.learned_nodes(owner, ascended_id))
            essences = await tx.essence_counts(owner)
            stored = await tx.get_loadout(owner, ascended_id)
        tree = self._catalog.ascended(ascended_id).tree
        nodes = []
        for node in tree.nodes:
            state, reason = self._state(node, record, learned, essences, tree)
            nodes.append({**node.to_public(), "state": state, "reason": reason})
        slots = self._slots(ascended_id, stored)
        loadout = {slot: slots.get(slot) for slot in (*ABILITY_SLOTS, PASSIVE_SLOT)}
        return {"ascended_id": ascended_id, "level": record.level, "essences": essences, "nodes": nodes, "loadout": loadout}

    async def loadout_in(self, tx: AscendedTransaction, owner: str, ascended_id: str) -> Loadout:
        """The kit a battle starts with, read inside the caller's transaction."""
        stored = await tx.get_loadout(owner, ascended_id)
        if not stored:
            return self._catalog.default_loadout(ascended_id)
        tree = self._catalog.ascended(ascended_id).tree
        learned = self._learned(ascended_id, await tx.learned_nodes(owner, ascended_id))
        abilities = []
        for slot in ABILITY_SLOTS:
            node = tree.node(stored.get(slot, ""))
            if node is not None and node.kind == "ability" and node.id in learned:
                abilities.append(node.ability)
        if not abilities:
            return self._catalog.default_loadout(ascended_id)
        passive_node = tree.node(stored.get(PASSIVE_SLOT, ""))
        passive = passive_node.passive if passive_node is not None and passive_node.kind == "passive" and passive_node.id in learned else NO_PASSIVE
        return Loadout(tuple(abilities), passive)

    # -- writes --------------------------------------------------------------------

    async def learn(self, owner: str, key: str, ascended_id: str, node_id: str) -> dict[str, Any]:
        async def work(tx: AscendedTransaction) -> dict[str, Any]:
            record = await self._owned(tx, owner, ascended_id)
            tree = self._catalog.ascended(ascended_id).tree
            node = tree.node(node_id)
            if node is None:
                raise InvalidRequest("there is no such node")
            learned = self._learned(ascended_id, await tx.learned_nodes(owner, ascended_id))
            essences = await tx.essence_counts(owner)
            if node.id in learned:
                raise UpgradeNotReady("that node is already learned")
            state, reason = self._state(node, record, learned, essences, tree)
            if state != "learnable":
                if reason and reason.endswith("essence"):
                    raise InsufficientEssence(f"{node.name} {reason}")
                raise UpgradeNotReady(f"{node.name} {reason}")
            await tx.add_essence(owner, node.cost.tier, -node.cost.amount)
            await tx.add_learned_node(owner, ascended_id, node.id)
            return {"kind": "learn", "ascended_id": ascended_id, "node_id": node.id,
                    "essence_tier": node.cost.tier, "essence_spent": node.cost.amount}

        return await self._writer.commit(owner, key, "tree.learn", {"ascended": ascended_id, "node": node_id}, work)

    async def set_loadout(self, owner: str, key: str, ascended_id: str, abilities: list[str], passive: str | None) -> dict[str, Any]:
        if not isinstance(abilities, list) or any(not isinstance(a, str) for a in abilities) or not (passive is None or isinstance(passive, str)):
            raise InvalidRequest("abilities must be a list of node ids and passive a node id or null")
        if not 1 <= len(abilities) <= len(ABILITY_SLOTS) or len(set(abilities)) != len(abilities):
            raise InvalidRequest(f"equip 1 to {len(ABILITY_SLOTS)} different abilities")

        async def work(tx: AscendedTransaction) -> dict[str, Any]:
            await self._owned(tx, owner, ascended_id)
            await self._reject_if_fighting(tx, owner, ascended_id)
            tree = self._catalog.ascended(ascended_id).tree
            learned = self._learned(ascended_id, await tx.learned_nodes(owner, ascended_id))

            def need(node_id: str, kind: str) -> None:
                node = tree.node(node_id)
                if node is None or node.kind != kind or node_id not in learned:
                    raise InvalidRequest(f"{node_id!r} is not a learned {kind} node of this Ascended")

            for node_id in abilities:
                need(node_id, "ability")
            if passive is not None:
                need(passive, "passive")
            slots = dict(zip(ABILITY_SLOTS, abilities))
            if passive is not None:
                slots[PASSIVE_SLOT] = passive
            await tx.put_loadout(owner, ascended_id, slots)
            return {"ascended_id": ascended_id, "abilities": list(abilities), "passive": passive}

        return await self._writer.commit(owner, key, "tree.loadout", {"ascended": ascended_id, "abilities": abilities, "passive": passive}, work)
