import asyncio

import pytest

from src.services.brain_connections import BrainError
from src.services.brain_suggestions import eligible_notes, parse_suggestions
from src.services.notes import NotesService
from tests.conftest import FakeDbGateway


def test_review_requires_private_consent_and_never_truncates():
    async def scenario():
        notes = NotesService(FakeDbGateway(), "alice")
        private = await notes.create("Private", "personal", agent_readable=False)
        public = await notes.create("Procedure", "durable", agent_readable=True)
        assert await eligible_notes(notes, [], []) == [public]
        with pytest.raises(BrainError, match="explicit"):
            await eligible_notes(notes, [private.id], [])
        assert await eligible_notes(notes, [private.id], [private.id]) == [private]
        for i in range(21):
            await notes.create(f"Procedure {i}", "x", agent_readable=True)
        with pytest.raises(BrainError, match="20"):
            await eligible_notes(notes, [], [])
    asyncio.run(scenario())


def test_untrusted_output_cannot_choose_unknown_note_or_unauthorized_destination():
    data = '{"suggestions":[{"note_id":"foreign","reason":"Good","title":"Title","folder":"Inbox","tags":[],"scope":"instance","draft":"Text"}]}'
    with pytest.raises(BrainError):
        parse_suggestions(data, {"owned"}, {"personal"})
    invalid = data.replace("foreign", "owned").replace("instance", "personal").replace("Inbox", "../escape")
    with pytest.raises(BrainError):
        parse_suggestions(invalid, {"owned"}, {"personal"})
