from src.core import internal_auth


def test_auto_save_scope_propagates_to_tools_and_delegates():
    requester = internal_auth.Requester.from_headers({"X-Requester-Uid": "alice", "X-Brain-Destination": "personal"})
    token = internal_auth.bind_requester(requester)
    try:
        assert internal_auth.requester_meta()["requester"]["brain_scope"] == "personal"
        assert internal_auth.outbound_headers()["X-Brain-Destination"] == "personal"
    finally:
        internal_auth.reset_requester(token)
    assert "X-Brain-Destination" not in internal_auth.outbound_headers()
