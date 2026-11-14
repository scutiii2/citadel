from src.providers import llm_config


def test_decision_gateway_files_hold_no_connection_or_key():
    """Addresses, keys, model, strategy and window are saved in DecisionGateway."""
    blocks = llm_config.load_gateways()["decision"]
    assert set(blocks) == {"laya", "jev"}
    assert all(set(block) == {"label"} for block in blocks.values())
