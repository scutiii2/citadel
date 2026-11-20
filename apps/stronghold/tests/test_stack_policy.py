from src.citadel_auth.policy import allowed, may_forward


def test_legion_may_call_the_mcp_server_and_forward_the_requester():
    assert allowed("stronghold", "legion", "/mcp")
    assert allowed("stronghold", "legion", "/mcp/")
    assert may_forward("stronghold", "legion")


def test_legion_has_no_other_stronghold_path():
    assert not allowed("stronghold", "legion", "/chats")
    assert not allowed("stronghold", "legion", "/stack/abc")


def test_armory_and_treasury_may_not_call_the_mcp_server():
    assert not allowed("stronghold", "armory", "/mcp")
    assert not allowed("stronghold", "treasury", "/mcp")
