import httpx
import pytest

from src.tool_services.outside import OutsideError, OutsideRegistry


class FakeTreasury:
    def __init__(self):
        self.origins = {}  # origin -> (service_id, origin_id)

    @staticmethod
    def _split(address):
        parts = address.split("/", 3)
        return "/".join(parts[:3]), ("/" + parts[3]) if len(parts) > 3 else ""

    async def post(self, path, body):
        assert set(body) <= {"address", "origin", "name"}
        origin, tail = self._split(body.get("address") or body["origin"])
        if path == "/outside/origins" and origin not in self.origins:
            if not body.get("name"):
                return httpx.Response(400, json={"error": "this address is new: give it a name"})
            self.origins[origin] = ("s-" + body["name"], f"o{len(self.origins) + 1}")
        found = self.origins.get(origin)
        group = None if found is None else {
            "service_id": found[0],
            "name": found[0][2:],
            "origins": [{"origin_id": origin_id, "origin": address}
                        for address, (service_id, origin_id) in self.origins.items() if service_id == found[0]],
            "used_by": ["stronghold"],
        }
        if path == "/outside/origins":
            return httpx.Response(200, json=group)
        return httpx.Response(200, json={"found": found is not None, "origin": origin, "path": tail,
                                         "origin_id": found[1] if found else None, "group": group})


@pytest.fixture
def registry(monkeypatch):
    fake = FakeTreasury()
    registry = OutsideRegistry(keyring=None, catalog=None)
    monkeypatch.setattr(registry, "_post", fake.post)
    return registry, fake


async def test_addresses_become_ids_and_an_override_is_kept_when_not_retyped(registry):
    reg, _ = registry
    first = await reg.entry_from_addresses(
        [{"address": "http://bard:29400", "name": "bard"}, {"address": "http://bard2:29400", "name": "bard", "header_value": "second"}], None)
    assert first == {"service_id": "s-bard", "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "second"}]}
    again = await reg.entry_from_addresses([{"address": "http://bard:29400"}, {"address": "http://bard2:29400"}], first)
    assert again["origins"][1] == {"origin_id": "o2", "header_value": "second"}


async def test_a_new_address_needs_a_name_and_one_service(registry):
    reg, fake = registry
    with pytest.raises(OutsideError, match="give it a name"):
        await reg.entry_from_addresses([{"address": "http://new:1"}], None)
    with pytest.raises(OutsideError, match="same outside service"):
        await reg.entry_from_addresses([{"address": "http://a:1", "name": "a"}, {"address": "http://b:1", "name": "b"}], None)
    with pytest.raises(OutsideError, match="listed twice"):
        await reg.entry_from_addresses([{"address": "http://a:1", "name": "a"}, {"address": "http://a:1/x", "name": "a"}], None)
    assert not fake.origins


async def test_treasury_down_refuses_with_1002(registry, monkeypatch):
    reg, _ = registry

    async def down(path, body):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(reg, "_post", down)
    with pytest.raises(OutsideError) as error:
        await reg.lookup("http://bard:29400")
    assert str(error.value).startswith("[1002]") and error.value.status == 502
