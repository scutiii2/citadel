import pytest

from src.gateway.conversation.presets import PRESETS
from src.gateway.conversation.store import ADDRESS, PROVIDERS, GatewayStore


@pytest.fixture
def store(tmp_path):
    return GatewayStore(tmp_path / "gateways.json")


def test_put_validates_and_hides_secrets(store):
    public = store.put("claude", {"provider": "anthropic", "api_key": "sk-1", "model": "claude-x"})
    assert public["has_api_key"] is True and "api_key" not in public and public["auth"] == "key" and public["timeout_s"] == 300
    assert store.all()["claude"]["api_key"] == "sk-1"
    assert "sk-1" not in str(store.public())


def test_update_keeps_secrets_when_left_out(store):
    store.put("claude", {"provider": "anthropic", "api_key": "sk-1", "model": "a"})
    store.put("claude", {"provider": "anthropic", "model": "b"})
    assert store.all()["claude"]["api_key"] == "sk-1" and store.all()["claude"]["model"] == "b"


def test_other_provider_does_not_inherit_old_values(store):
    store.put("x", {"provider": "anthropic", "api_key": "sk-1", "model": "a"})
    with pytest.raises(ValueError):
        store.put("x", {"provider": "openai", "model": "m", "api": "chat"} | {"auth": "azure"})  # azure fields missing, no old key


@pytest.mark.parametrize("gid,data,part", [
    ("Bad Id", {"provider": "scuti", "url": "http://127.0.0.1:1"}, "id"),
    ("a", "text", "object"),
    ("a", {"provider": "nope"}, "provider"),
    ("a", {"provider": "anthropic", "model": "m"}, "API key"),
    ("a", {"provider": "anthropic", "api_key": "k"}, "model"),
    ("a", {"provider": "anthropic", "auth": "bedrock", "model": "m", "aws_region": "us-east-1"}, "AWS"),
    ("a", {"provider": "anthropic", "api_key": "k", "model": "m", "base_url": "http://u:p@host"}, "address"),
    ("a", {"provider": "openai", "api": "weird", "api_key": "k", "model": "m"}, "api"),
    ("a", {"provider": "openai", "api_key": "k", "model": "m", "max_tokens_param": "x"}, "max_tokens_param"),
    ("a", {"provider": "scuti"}, "address"),
    ("a", {"provider": "scuti", "url": "http://127.0.0.1:1", "timeout_s": 0}, "timeout"),
    ("a", {"provider": "scuti", "url": "http://127.0.0.1:1", "capabilities": {"tools": "yes"}}, "capabilities"),
    ("a", {"provider": "scuti", "url": "http://127.0.0.1:1", "capabilities": {"magic": True}}, "capabilities"),
    ("a", {"provider": "scuti", "url": "http://127.0.0.1:1", "max_tokens_limit": 0}, "max_tokens_limit"),
])
def test_bad_entries(store, gid, data, part):
    with pytest.raises(ValueError) as error:
        store.put(gid, data)
    assert part.lower() in str(error.value).lower()


def test_openai_local_server_needs_no_key_but_a_base_url(store):
    store.put("ollama", {"provider": "openai", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen"})
    with pytest.raises(ValueError):
        store.put("nokey", {"provider": "openai", "model": "m"})


def test_scuti_entry(store):
    public = store.put("minicpm", {"provider": "scuti", "url": "http://127.0.0.1:29200/", "token": "t", "project": "demo",
                                   "capabilities": {"tools": True}, "max_tokens_limit": 8192})
    assert public["url"] == "http://127.0.0.1:29200" and public["has_token"] is True and public["capabilities"] == {"tools": True}


def test_delete(store):
    store.put("a", {"provider": "scuti", "url": "http://127.0.0.1:1"})
    assert store.delete("a") is True and store.delete("a") is False and store.all() == {}


def test_every_preset_is_a_valid_entry_once_the_user_fills_the_gaps(store):
    secrets = {"api_key", "token", "aws_access_key_id", "aws_secret_access_key"}
    for name, entry in PRESETS.items():
        assert not secrets & set(entry), f"{name} holds a secret"
        filled = dict(entry)
        for field, _label, _secret, required in PROVIDERS[entry["provider"]][entry.get("auth", "")]:
            if required and not filled.get(field):
                filled[field] = "http://x.test" if field in ADDRESS else "x"
        if not filled.get("model"):
            filled["model"] = "x"
        filled.setdefault("api_key", "x")  # OpenAI itself needs a key; fields a variant does not use are ignored
        store.put(name, filled)
    assert {"gemini", "claude", "gpt", "minicpm", "bitnet", "lfm3", "sparkx"} <= set(PRESETS)


def test_tier_models_are_saved_trimmed_and_cleared(store):
    saved = store.put("vllm", {"provider": "openai", "base_url": "http://h:8000/v1", "model": "m",
                               "models": {"light": " small ", "heavy": "", "extreme": "big"}})
    assert saved["models"] == {"light": "small", "extreme": "big"}
    assert store.put("vllm", {"provider": "openai", "base_url": "http://h:8000/v1", "model": "m"})["models"] == {"light": "small", "extreme": "big"}
    assert "models" not in store.put("vllm", {"provider": "openai", "base_url": "http://h:8000/v1", "model": "m", "models": {}})


@pytest.mark.parametrize("models", [{"huge": "x"}, {"light": 3}, "light"])
def test_tier_models_are_checked(store, models):
    with pytest.raises(ValueError):
        store.put("vllm", {"provider": "openai", "base_url": "http://h:8000/v1", "model": "m", "models": models})


def test_model_list_links_are_https_and_only_on_presets_that_have_a_public_list():
    linked = {name for name, entry in PRESETS.items() if "models_url" in entry}
    assert all(PRESETS[name]["models_url"].startswith("https://") for name in linked)
    assert {"claude", "gpt", "openrouter"} <= linked and not linked & {"minicpm", "bitnet", "lfm3", "sparkx", "omniroute"}


def test_self_hosted_presets_start_from_their_usual_local_address():
    assert PRESETS["litellm"]["base_url"] == "http://host.docker.internal:4000" and PRESETS["vllm"]["base_url"] == "http://host.docker.internal:8000/v1"


def test_freellmapi_preset_is_openai_chat_on_its_service_port_with_no_public_list():
    preset = PRESETS["freellmapi"]
    assert (preset["provider"], preset["api"], preset["base_url"]) == ("openai", "chat", "http://host.docker.internal:29652/v1")
    assert "models_url" not in preset and preset["dashboard_port"] == 29652


def test_omniroute_has_no_public_list_but_names_its_dashboard_port():
    assert "models_url" not in PRESETS["omniroute"] and PRESETS["omniroute"]["dashboard_port"] == 29651
