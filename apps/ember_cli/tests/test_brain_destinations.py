"""Transport contract checks independent of the terminal renderer's optional rich dependency."""
import asyncio
import json

import httpx

from src.api import EmberClient, _summary


def test_old_chat_defaults_to_shared_and_personal_scope_survives_parsing():
    base = {"id": "chat", "title": "Title"}
    assert _summary(base).second_brain_scope == "instance"
    assert not _summary(base).save_to_second_brain
    saved = _summary({**base, "save_to_second_brain": True, "second_brain_scope": "personal"})
    assert saved.save_to_second_brain and saved.second_brain_scope == "personal"


def test_optional_destination_is_sent_only_when_explicit():
    async def scenario():
        bodies = []
        def handler(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(202, json={"sequence": 1})
        client = EmberClient("http://ember.test", transport=httpx.MockTransport(handler))
        try:
            await client.start_turn("chat", "Question", "entry")
            await client.start_turn("chat", "Question", "entry", save_to_second_brain=True, second_brain_scope="personal")
        finally:
            await client.aclose()
        assert "second_brain_scope" not in bodies[0]
        assert bodies[1]["second_brain_scope"] == "personal"
    asyncio.run(scenario())
