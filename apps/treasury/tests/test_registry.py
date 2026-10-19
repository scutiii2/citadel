import pytest

from src.backends.factory import build_backend
from src.registry import (
    ConnectionRegistry, InstanceManager, RawSqlDisabled, UnknownConnection, UnknownInstance,
)
from tests.conftest import memory_spec


def make_manager(builds: list[str]):
    specs = {"a": memory_spec("a"), "b": memory_spec("b", raw_sql=True)}

    def build(spec):
        builds.append(spec.name)
        return build_backend(spec)

    registry = ConnectionRegistry(specs, build)
    return InstanceManager({"one": ("a", "b"), "two": ("a",)}, registry), registry


async def test_connection_is_lazy_and_opened_once():
    builds: list[str] = []
    manager, registry = make_manager(builds)
    assert builds == []
    one, two = manager.get("one"), manager.get("two")
    first = await one.backend("a")
    second = await two.backend("a")
    assert first is second  # same connection, same cache
    assert builds == ["a"]
    await manager.close()


async def test_instances_share_data_through_one_connection():
    manager, _ = make_manager([])
    await (await manager.get("one").backend("a")).put("c", "k", {"v": 1})
    assert await (await manager.get("two").backend("a")).get("c", "k") == {"v": 1}
    await manager.close()


async def test_connection_closes_when_last_instance_releases():
    manager, registry = make_manager([])
    one, two = manager.get("one"), manager.get("two")
    await one.backend("a")
    await two.backend("a")
    await one.close()
    assert registry.open_names() == ["a"]
    await two.close()
    assert registry.open_names() == []


async def test_instance_cannot_reach_foreign_connection():
    manager, _ = make_manager([])
    with pytest.raises(UnknownConnection):
        await manager.get("two").backend("b")
    with pytest.raises(UnknownInstance):
        manager.get("nope")


async def test_raw_sql_gate():
    manager, _ = make_manager([])
    one = manager.get("one")
    with pytest.raises(RawSqlDisabled):
        await one.sql_backend("a")
    assert await one.sql_backend("b")
    await manager.close()
