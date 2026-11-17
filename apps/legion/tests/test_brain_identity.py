from src.runtime import internal_auth


def test_auto_save_scope_propagates_to_tools_and_delegates(auth_stack):
    from src.citadel_auth import mint_requester
    signed = mint_requester(auth_stack["portcullis"], "alice", "alice", "", ["legion", "armory"])
    requester = internal_auth.Requester(uid="alice", brain_scope="personal", requester_token=signed)
    token = internal_auth.bind_requester(requester)
    try:
        assert internal_auth.requester_meta()["brain_scope"] == "personal"
        assert internal_auth.requester_meta()["requester_token"] == signed
        assert internal_auth.outbound_headers()["X-Brain-Destination"] == "personal"
    finally:
        internal_auth.reset_requester(token)
    assert "X-Brain-Destination" not in internal_auth.outbound_headers()
