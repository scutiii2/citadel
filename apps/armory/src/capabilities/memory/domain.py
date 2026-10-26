"""Typed memory operations; memory_store owns storage, identity_context the owner."""
from src.capabilities.memory.contract import ClearResult, ForgetResult, SaveResult, SearchResult
from src.config import settings
from src.services import identity_context, untrusted
from src.capabilities.memory.utils import memory_store
from src.services.internal_token import is_exposed_without_token


class MemoryDesk:
    """The signed-in owner's saved memory notes; every method checks identity first."""

    def _owner(self) -> str:
        """The caller's uid, after checking that the identity can be trusted at all."""
        if is_exposed_without_token(settings.host, settings.internal_api_token):
            # Without the token any machine that can reach the port could claim any uid.
            raise memory_store.MemoryStoreError(
                f"Memory is disabled: this server listens on {settings.host!r} without INTERNAL_API_TOKEN, "
                "so anyone on the network could read saved notes. Set INTERNAL_API_TOKEN, or bind to 127.0.0.1."
            )
        return identity_context.current_uid()

    def save(self, text: str) -> SaveResult:
        outcome = memory_store.save(settings.memory_db_path, self._owner(), text)
        if outcome.duplicate:
            return SaveResult(id=outcome.id, message=f"That is already saved as note {outcome.id}; nothing changed.")
        return SaveResult(id=outcome.id, message=f"Saved as note {outcome.id}.")

    def search(self, query: str = "") -> SearchResult:
        notes = memory_store.search(settings.memory_db_path, self._owner(), query)
        if not notes:
            return SearchResult(count=0, message="No saved notes match." if query.strip() else "No saved notes yet.")
        lines = [f"[{note.id}] {note.created_at[:10]}: {note.text}" for note in notes]
        # Note text was typed by a user or written by the model earlier: treat it as data.
        body = untrusted.fence("\n".join(lines), source="your saved memory notes")
        return SearchResult(count=len(notes), message=f"{len(notes)} saved note(s):\n{body}")

    def clear(self) -> ClearResult:
        count = memory_store.purge_owner(settings.memory_db_path, self._owner())
        return ClearResult(count=count, message=f"Deleted {count} saved note(s)." if count else "There were no saved notes to delete.")

    def forget(self, note_id: int) -> ForgetResult:
        if memory_store.forget(settings.memory_db_path, self._owner(), note_id):
            return ForgetResult(forgotten=True, message=f"Forgot note {note_id}.")
        return ForgetResult(forgotten=False, message=f"No note {note_id} found among your saved notes.")


desk = MemoryDesk()
