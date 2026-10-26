from src.providers import llm_config


def test_decision_gateways_are_listed():
    blocks = llm_config.load_gateways()["decision"]
    assert blocks["laya"]["strategy"] == "english-then-typed"
    assert blocks["jev"]["url"] == "https://api.typesafe.ai/v1/systemone"
    assert blocks["jev"]["model"] == "jev-latest"
    assert blocks["jev"]["api_key"] == "{TYPESAFE_API_KEY}"
