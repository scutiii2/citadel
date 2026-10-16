import asyncio

from src.backends.sqlite import SqliteBackend
from src.cache import CachedBackend, CacheSettings, TtlLruCache
from tests.conftest import CountingBackend


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def make(settings=CacheSettings(ttl_seconds=10, max_entries=100, negative_ttl_seconds=2), clock=None):
    counter = CountingBackend(SqliteBackend(":memory:"))
    cached = CachedBackend(counter, settings, clock or Clock())
    await cached.connect()
    return cached, counter


def test_ttl_and_lru_eviction():
    clock = Clock()
    cache = TtlLruCache(2, clock)
    cache.set("a", 1, ttl=10)
    cache.set("b", 2, ttl=10)
    cache.get("a")  # a is now most recent
    cache.set("c", 3, ttl=10)  # evicts b
    assert cache.get("a") == 1 and cache.get("c") == 3
    assert len(cache) == 2  # b was evicted
    clock.now = 11
    cache.get("a")  # expired entries drop on read
    assert len(cache) == 1


async def test_second_read_skips_database():
    cached, counter = await make()
    await cached.put("c", "k", {"v": 1})
    assert await cached.get("c", "k") == {"v": 1}
    assert await cached.get("c", "k") == {"v": 1}
    assert counter.calls["get"] == 1


async def test_ttl_expiry_rereads():
    clock = Clock()
    cached, counter = await make(clock=clock)
    await cached.put("c", "k", {"v": 1})
    await cached.get("c", "k")
    clock.now = 11
    await cached.get("c", "k")
    assert counter.calls["get"] == 2


async def test_write_invalidates_record_and_queries():
    cached, counter = await make()
    await cached.put("c", "k", {"v": 1})
    await cached.get("c", "k")
    assert await cached.query("c", {"v": 1}) == [{"v": 1}]
    await cached.put("c", "k", {"v": 2})
    assert (await cached.get("c", "k"))["v"] == 2
    assert await cached.query("c", {"v": 1}) == []
    assert counter.calls["query"] == 2
    await cached.delete("c", "k")
    assert await cached.get("c", "k") is None


async def test_negative_caching_and_expiry():
    clock = Clock()
    cached, counter = await make(clock=clock)
    assert await cached.get("c", "missing") is None
    assert await cached.get("c", "missing") is None
    assert counter.calls["get"] == 1
    clock.now = 3  # past negative ttl of 2
    await cached.get("c", "missing")
    assert counter.calls["get"] == 2


async def test_mutating_a_result_does_not_poison_cache():
    cached, _ = await make()
    await cached.put("c", "k", {"v": 1})
    first = await cached.get("c", "k")
    first["v"] = 99
    assert (await cached.get("c", "k"))["v"] == 1


async def test_concurrent_misses_share_one_database_call():
    cached, counter = await make()
    await cached.put("c", "k", {"v": 1})
    results = await asyncio.gather(*(cached.get("c", "k") for _ in range(10)))
    assert all(r == {"v": 1} for r in results)
    assert counter.calls["get"] == 1


async def test_raw_sql_clears_cache():
    cached, counter = await make()
    await cached.put("c", "k", {"v": 1})
    await cached.get("c", "k")
    await cached.execute_sql("DELETE FROM documents")
    assert await cached.get("c", "k") is None
    assert counter.calls["get"] == 2


async def test_ttl_zero_disables_cache_in_factory():
    from src.backends.factory import build_backend
    from tests.conftest import memory_spec

    assert not isinstance(build_backend(memory_spec("x", ttl=0)), CachedBackend)
    assert isinstance(build_backend(memory_spec("x", ttl=5)), CachedBackend)
