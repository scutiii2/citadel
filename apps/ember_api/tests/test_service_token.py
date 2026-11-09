from src.utils.config_loader import service_token


def test_service_token_reads_env_then_file_and_never_the_shared_token(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("BARD_TOKEN=from-file\nINTERNAL_API_TOKEN=shared\n", encoding="utf-8")
    monkeypatch.delenv("BARD_TOKEN", raising=False)
    monkeypatch.delenv("SCRIBE_TOKEN", raising=False)
    assert service_token(env_file, "bard") == "from-file"
    assert service_token(env_file, "scribe") == ""
    monkeypatch.setenv("BARD_TOKEN", "from-env")
    assert service_token(env_file, "bard") == "from-env"
