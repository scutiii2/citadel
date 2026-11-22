from src.runtime import internal_auth


def test_a_requester_carries_no_brain_destination():
    import dataclasses

    assert "brain_scope" not in {f.name for f in dataclasses.fields(internal_auth.Requester)}


def test_outbound_calls_never_send_a_brain_destination(auth_stack):
    from src.citadel_auth import mint_requester
    signed = mint_requester(auth_stack["portcullis"], "alice", "alice", "", ["legion", "armory"])
    requester = internal_auth.Requester(uid="alice", requester_token=signed)
    token = internal_auth.bind_requester(requester)
    try:
        assert internal_auth.requester_meta()["requester_token"] == signed
        assert "brain_scope" not in internal_auth.requester_meta()
        assert "X-Brain-Destination" not in internal_auth.outbound_headers()
    finally:
        internal_auth.reset_requester(token)
