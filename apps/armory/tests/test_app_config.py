"""Tests for services/app_config.py.
It fails loudly, so most tests assert on the error, not the happy path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.citadel_auth import settings_store
from src.services.app_config import (
    EmailConfig,
    ExtensionConfig,
    capability_enabled,
    delete_extension_config,
    load_capabilities_config,
    load_config,
    load_email_config,
    load_extension_config,
    load_extensions_config,
    migrate_renamed_capabilities,
    resolve_section,
    save_capabilities_config,
    save_extension_config,
)


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _email(tmp_path: Path, document: dict) -> Path:
    """A settings store holding this SMTP document."""
    path = tmp_path / "settings.db"
    settings_store.put(path, "email", "smtp", document)
    return path


def _store(tmp_path: Path, extensions: dict) -> Path:
    """A settings store holding these extensions."""
    path = tmp_path / "settings.db"
    for key, entry in extensions.items():
        settings_store.put(path, "extensions", key, entry)
    return path


def _caps(tmp_path: Path, capabilities: dict) -> Path:
    """A settings store holding these capability entries."""
    path = tmp_path / "settings.db"
    for key, entry in capabilities.items():
        settings_store.put(path, "capabilities", key, entry)
    return path


def _resolve(path: Path, name: str):
    """Resolve one top-level key as a caller resolving an arbitrary subtree would; tests ``resolve_section`` itself."""
    return resolve_section(load_config(path)[name], where=name, config_path=path)


VALID_EMAIL = {
    "smtp_server": "smtp.example.com",
    "smtp_port": 587,
    "from": "notifications@example.com",
    "password": "changeme",
    "to": ["team@example.com"],
}

VALID_EXTENSIONS = {
    "reference": {
        "label": "Reference Extension",
        "description": "Dev fixture",
        "command": "python",
        "args": ["-m", "src._fixtures.reference_extension_server"],
    },
    "other": {
        "label": "Other Extension",
        "description": "Another one",
        "command": "python",
        "args": [],
    },
}


# --- email settings ---
# Email settings live in the settings database as literal values; ${VAR} resolution (resolve_section) still serves the extension and file configs.


def test_literal_empty_string_is_still_allowed(tmp_path: Path):
    """The documented escape hatch: write "" directly if empty is intended."""
    path = _email(tmp_path, {**VALID_EMAIL, "password": ""})

    assert load_email_config(path).password == ""


def test_non_string_values_pass_through_untouched(tmp_path: Path):
    path = _write(tmp_path, {"email": VALID_EMAIL, "extras": {"count": 3, "on": True, "nothing": None}})

    assert _resolve(path, "extras") == {"count": 3, "on": True, "nothing": None}


def test_bare_dollar_signs_are_not_treated_as_placeholders(tmp_path: Path):
    """Only ${NAME} interpolates - a lone "$" is ordinary text, so shell-ish
    or currency strings survive intact."""
    path = _write(tmp_path, {"email": VALID_EMAIL, "note": "costs US$5, not $HOME"})

    assert _resolve(path, "note") == "costs US$5, not $HOME"


def test_double_dollar_escapes_a_literal_placeholder(tmp_path: Path, monkeypatch):
    """Without an escape, text that genuinely contains ${...} could not be stored."""
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    path = _write(tmp_path, {"email": VALID_EMAIL, "note": "write $${SMTP_PASSWORD} to refer to it"})

    assert _resolve(path, "note") == "write ${SMTP_PASSWORD} to refer to it"


def test_double_dollar_outside_a_placeholder_becomes_one_dollar(tmp_path: Path):
    path = _write(tmp_path, {"email": VALID_EMAIL, "note": "costs 5$$"})

    assert _resolve(path, "note") == "costs 5$"


def test_placeholder_value_is_not_itself_expanded(tmp_path: Path, monkeypatch):
    """No recursive expansion: a value containing ${...} is used literally."""
    monkeypatch.setenv("WEIRD", "${NOT_A_VAR}")
    monkeypatch.delenv("NOT_A_VAR", raising=False)
    path = _write(tmp_path, {"email": VALID_EMAIL, "note": "${WEIRD}"})

    assert _resolve(path, "note") == "${NOT_A_VAR}"


def test_load_config_leaves_placeholders_unresolved(tmp_path: Path, monkeypatch):
    """load_config only parses and validates; the placeholder must survive verbatim, or every secret would be demanded."""
    monkeypatch.delenv("DESKTOP_SSH_PASSWORD", raising=False)
    path = _write(tmp_path, {"desktop": {"password": "${DESKTOP_SSH_PASSWORD}"}})

    assert load_config(path)["desktop"]["password"] == "${DESKTOP_SSH_PASSWORD}"


# --- file handling -----------------------------------------------------


def test_load_config_returns_the_parsed_object(tmp_path: Path):
    path = _write(tmp_path, {"email": VALID_EMAIL})
    assert load_config(path) == {"email": VALID_EMAIL}


def test_missing_file_raises_and_names_the_path(tmp_path: Path):
    missing = tmp_path / "nope.json"
    with pytest.raises(FileNotFoundError, match="nope.json"):
        load_config(missing)


def test_invalid_json_raises_rather_than_returning_empty(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_config(path)


def test_top_level_array_is_rejected(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_config(path)


def test_load_email_config_maps_from_to_from_address(tmp_path: Path):
    """``from`` is a Python keyword, so the dataclass field can't share its
    name - this is the one place that rename happens."""
    path = _email(tmp_path, VALID_EMAIL)

    config = load_email_config(path)

    assert config == EmailConfig(
        smtp_server="smtp.example.com",
        smtp_port=587,
        from_address="notifications@example.com",
        password="changeme",
        to=["team@example.com"],
    )


def test_missing_required_key_names_the_key(tmp_path: Path):
    incomplete = {k: v for k, v in VALID_EMAIL.items() if k != "smtp_server"}
    path = _email(tmp_path, incomplete)
    with pytest.raises(KeyError, match="smtp_server"):
        load_email_config(path)


def test_to_may_be_omitted_entirely(tmp_path: Path):
    """A deployment mailing only caller-supplied addresses has no standing recipient list; requiring one would force an invented address."""
    no_to = {k: v for k, v in VALID_EMAIL.items() if k != "to"}
    path = _email(tmp_path, no_to)

    config = load_email_config(path)

    assert config.to == []


def test_to_and_domains_may_be_absent(tmp_path: Path):
    """Load time is the wrong place to reject this: send_email raises "No recipients" at the moment it matters."""
    no_to = {k: v for k, v in VALID_EMAIL.items() if k != "to"}
    path = _email(tmp_path, {**no_to, "allowed_recipient_domains": ["example.com"]})

    config = load_email_config(path)

    assert config.to == []
    assert config.allowed_recipient_domains == ["example.com"]


def test_password_may_be_omitted_entirely(tmp_path: Path):
    """An unauthenticated send is a real config (LAN relay); demanding the key would force a dummy password offered to a server without AUTH."""
    no_password = {k: v for k, v in VALID_EMAIL.items() if k != "password"}
    path = _email(tmp_path, no_password)

    assert load_email_config(path).password == ""


def test_security_defaults_to_starttls_on_a_submission_port(tmp_path: Path):
    path = _email(tmp_path, VALID_EMAIL)

    assert load_email_config(path).security == "starttls"


def test_port_465_infers_implicit_tls(tmp_path: Path):
    """465 is the implicit-TLS port every mainstream provider uses, so the port implies the transport."""
    path = _email(tmp_path, {**VALID_EMAIL, "smtp_port": 465})

    assert load_email_config(path).security == "ssl"


def test_explicit_security_beats_the_port_inference(tmp_path: Path):
    """Inference is a convenience, not a rule: a relay can listen for
    STARTTLS on 465, and the config file has to win when it disagrees."""
    path = _email(tmp_path, {**VALID_EMAIL, "smtp_port": 465, "security": "starttls"})

    assert load_email_config(path).security == "starttls"


def test_security_is_normalized(tmp_path: Path):
    path = _email(tmp_path, {**VALID_EMAIL, "security": " SSL "})

    assert load_email_config(path).security == "ssl"


def test_unsupported_security_is_rejected_rather_than_falling_back(tmp_path: Path):
    """A typo must not quietly become a plaintext connection: the password
    would go out in the clear and nothing in the run would say so."""
    path = _email(tmp_path, {**VALID_EMAIL, "security": "tls"})

    with pytest.raises(ValueError, match="expected one of"):
        load_email_config(path)


def test_single_recipient_string_is_accepted_as_a_list(tmp_path: Path):
    """A bare string is the obvious way to write one recipient; iterating it per character would be a nasty surprise."""
    path = _email(tmp_path, {**VALID_EMAIL, "to": "solo@example.com"})

    assert load_email_config(path).to == ["solo@example.com"]


def test_string_port_is_coerced_to_int(tmp_path: Path):
    path = _email(tmp_path, {**VALID_EMAIL, "smtp_port": "587"})

    assert load_email_config(path).smtp_port == 587


# --- allowed_recipient_domains ---
# The loader must produce exactly what the operator wrote, and nothing when they wrote nothing.


def test_omitting_allowed_recipient_domains_allows_no_domains(tmp_path: Path):
    """The dangerous default, tested directly: an absent key must mean "no domains", never "any domain"."""
    path = _email(tmp_path, VALID_EMAIL)

    assert load_email_config(path).allowed_recipient_domains == []


def test_allowed_recipient_domains_are_loaded_in_order(tmp_path: Path):
    path = _email(tmp_path, {**VALID_EMAIL, "allowed_recipient_domains": ["example.com", "example.org"]})

    assert load_email_config(path).allowed_recipient_domains == ["example.com", "example.org"]


def test_domains_are_normalized_to_bare_lowercase(tmp_path: Path):
    """People write "@example.com" or ".example.com" as readily as the bare form, and domains are case-insensitive.
    A config that looks right but matches nothing is the worst outcome."""
    path = _email(
        tmp_path,
        {
            **VALID_EMAIL,
            "allowed_recipient_domains": ["  Example.COM ", "@Corp.example", ".mail.example"],
        },
    )

    assert load_email_config(path).allowed_recipient_domains == [
        "example.com",
        "corp.example",
        "mail.example",
    ]


def test_blank_domain_entries_are_dropped(tmp_path: Path):
    """A leftover "" can only fail to match, but would appear in refusal messages."""
    path = _email(tmp_path, {**VALID_EMAIL, "allowed_recipient_domains": ["", "  "]})

    assert load_email_config(path).allowed_recipient_domains == []


def test_a_single_domain_string_is_accepted_as_a_list(tmp_path: Path):
    """Same reasoning as 'to': iterating a bare string character by
    character would produce a list of one-letter domains."""
    path = _email(tmp_path, {**VALID_EMAIL, "allowed_recipient_domains": "example.com"})

    assert load_email_config(path).allowed_recipient_domains == ["example.com"]


# --- extensions ---
# Per-entry resolution and broken-sibling isolation: one unset variable must not break other extensions.


def test_extensions_are_keyed_by_id(tmp_path: Path):
    path = _store(tmp_path, VALID_EXTENSIONS)

    extensions = load_extensions_config(path)

    assert set(extensions) == {"reference", "other"}
    assert extensions["reference"].id == "reference"
    assert extensions["reference"].command == "python"
    assert extensions["reference"].args == ["-m", "src._fixtures.reference_extension_server"]


def test_args_default_to_empty_list(tmp_path: Path):
    no_args = {k: v for k, v in VALID_EXTENSIONS["reference"].items() if k != "args"}
    path = _store(tmp_path, {"reference": no_args})

    assert load_extensions_config(path)["reference"].args == []


def test_description_defaults_to_empty_string(tmp_path: Path):
    """Unlike `label` or `command`, a missing description degrades gracefully; it's cosmetic."""
    no_description = {k: v for k, v in VALID_EXTENSIONS["reference"].items() if k != "description"}
    path = _store(tmp_path, {"reference": no_description})

    assert load_extensions_config(path)["reference"].description == ""


def test_missing_command_and_url_is_rejected(tmp_path: Path):
    """'command' xor 'url' is required, so omitting 'command' alone with no 'url' raises the mutual-exclusion ValueError, not a KeyError.
    (see test_extension_with_neither_command_nor_url_is_rejected)"""
    no_command = {k: v for k, v in VALID_EXTENSIONS["reference"].items() if k != "command"}
    path = _store(tmp_path, {"reference": no_command})

    with pytest.raises(ValueError, match="'command'.*'url'"):
        load_extensions_config(path)


def test_missing_label_names_the_entry_and_the_key(tmp_path: Path):
    no_label = {k: v for k, v in VALID_EXTENSIONS["reference"].items() if k != "label"}
    path = _store(tmp_path, {"reference": no_label})

    with pytest.raises(KeyError, match="reference.label"):
        load_extensions_config(path)


def test_extension_args_resolve_placeholders(tmp_path: Path, monkeypatch):
    """The documented future use case: a bearer token passed as a CLI
    arg, named rather than written down, same as hosts.<name>.password."""
    monkeypatch.setenv("REFERENCE_TOKEN", "s3cret")
    path = _store(
        tmp_path,
        {"reference": {**VALID_EXTENSIONS["reference"], "args": ["--token", "${REFERENCE_TOKEN}"]}},
    )

    assert load_extensions_config(path)["reference"].args == ["--token", "s3cret"]


def test_a_broken_extension_does_not_break_a_sibling_extension(tmp_path: Path, monkeypatch):
    """Resolution is per entry: one extension's unset secret can't take a working sibling down."""
    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    path = _store(
        tmp_path,
        {
            "reference": VALID_EXTENSIONS["reference"],
            "broken": {**VALID_EXTENSIONS["other"], "args": ["${MISSING_TOKEN}"]},
        },
    )

    assert load_extension_config(path, "reference").command == "python"

    with pytest.raises(KeyError, match="MISSING_TOKEN"):
        load_extension_config(path, "broken")


def test_loading_all_extensions_still_fails_when_any_is_broken(tmp_path: Path, monkeypatch):
    """The one caller that needs every extension returns the whole set; skipping the broken one would silently shorten it."""
    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    path = _store(
        tmp_path,
        {
            "reference": VALID_EXTENSIONS["reference"],
            "broken": {**VALID_EXTENSIONS["other"], "args": ["${MISSING_TOKEN}"]},
        },
    )

    with pytest.raises(KeyError, match="MISSING_TOKEN"):
        load_extensions_config(path)


def test_unknown_extension_names_the_ones_that_exist(tmp_path: Path):
    path = _store(tmp_path, VALID_EXTENSIONS)

    with pytest.raises(KeyError, match="other, reference"):
        load_extension_config(path, "nope")


def test_an_extension_entry_that_is_not_an_object_is_rejected(tmp_path: Path):
    path = _store(tmp_path, {"reference": "not-a-dict"})

    with pytest.raises(ValueError, match="must be an object"):
        load_extensions_config(path)


def test_extension_entry_args_must_be_a_list(tmp_path: Path):
    path = _store(tmp_path, {"reference": {**VALID_EXTENSIONS["reference"], "args": "not-a-list"}})

    with pytest.raises(ValueError, match="must be a list"):
        load_extensions_config(path)


def test_load_extensions_config_returns_extension_config_instances(tmp_path: Path):
    path = _store(tmp_path, {"reference": VALID_EXTENSIONS["reference"]})

    assert load_extensions_config(path)["reference"] == ExtensionConfig(
        id="reference",
        label="Reference Extension",
        description="Dev fixture",
        transport="stdio",
        command="python",
        args=["-m", "src._fixtures.reference_extension_server"],
    )


# --- extensions: http transport ---
# Connect to a URL instead of spawning a subprocess; 'command' and 'url' are mutually exclusive, exactly one required.


def test_http_extension_entry_parses_correctly(tmp_path: Path):
    path = _store(
        tmp_path,
        {
            "remote": {
                "label": "Remote Extension",
                "description": "An http-transport extension",
                "url": "http://127.0.0.1:9000/mcp",
            }
        },
    )

    config = load_extensions_config(path)["remote"]

    assert config == ExtensionConfig(
        id="remote",
        label="Remote Extension",
        description="An http-transport extension",
        transport="http",
        url="http://127.0.0.1:9000/mcp",
    )


def test_extension_with_both_command_and_url_is_rejected(tmp_path: Path):
    path = _store(
        tmp_path,
        {"confused": {"label": "Confused", "command": "python", "url": "http://127.0.0.1:9000/mcp"}},
    )

    with pytest.raises(ValueError, match="both 'command' and 'url'"):
        load_extensions_config(path)


def test_extension_with_neither_command_nor_url_is_rejected(tmp_path: Path):
    path = _store(tmp_path, {"nothing": {"label": "Nothing"}})

    with pytest.raises(ValueError, match="'command'.*'url'"):
        load_extensions_config(path)


def test_http_extension_url_resolves_placeholders(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("UPSTREAM_HOST", "upstream.internal")
    path = _store(tmp_path, {"remote": {"label": "Remote", "url": "http://${UPSTREAM_HOST}:9000/mcp"}})

    assert load_extensions_config(path)["remote"].url == "http://upstream.internal:9000/mcp"


def test_http_extension_empty_url_is_rejected(tmp_path: Path):
    path = _store(tmp_path, {"remote": {"label": "Remote", "url": "   "}})

    with pytest.raises(ValueError, match="must not be empty"):
        load_extensions_config(path)


def test_http_extension_headers_resolve_placeholders(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PDF_MERGER_TOKEN", "s3cret")
    path = _store(
        tmp_path,
        {
            "pdf_merger": {
                "label": "PDF Merger",
                "url": "http://127.0.0.1:8040/mcp",
                "headers": {"X-Internal-Token": "${PDF_MERGER_TOKEN}"},
            }
        },
    )

    assert load_extensions_config(path)["pdf_merger"].headers == {"X-Internal-Token": "s3cret"}


def test_legacy_shared_token_placeholder_is_rejected_even_if_set(tmp_path: Path, monkeypatch):
    name = "INTERNAL_" + "API_TOKEN"
    monkeypatch.setenv(name, "must-not-be-used")
    path = _store(tmp_path, {"legacy": {"label": "Legacy", "url": "http://legion/mcp",
                                      "headers": {"Authorization": "${" + name + "}"}}})
    with pytest.raises(ValueError, match="unsupported"):
        load_extensions_config(path)


def test_http_extension_without_headers_has_none(tmp_path: Path):
    path = _store(tmp_path, {"remote": {"label": "Remote", "url": "http://127.0.0.1:9000/mcp"}})

    assert load_extensions_config(path)["remote"].headers == {}


def test_http_extension_headers_must_be_strings(tmp_path: Path):
    path = _store(tmp_path, {"remote": {"label": "Remote", "url": "http://127.0.0.1:9000/mcp", "headers": {"X-Count": 3}}})

    with pytest.raises(ValueError, match="'remote.headers' must be an object of string values"):
        load_extensions_config(path)


def test_stdio_extension_with_headers_is_rejected(tmp_path: Path):
    path = _store(tmp_path, {"local": {"label": "Local", "command": "python", "headers": {"X": "y"}}})

    with pytest.raises(ValueError, match="'local.headers' only applies to an http extension"):
        load_extensions_config(path)


# --- save_extension_config / delete_extension_config ---
# The runtime add/remove routes persist through these, so they must round-trip and leave other entries untouched.


def test_save_extension_config_adds_a_new_http_entry(tmp_path: Path):
    path = _store(tmp_path, {})

    save_extension_config(
        path,
        ExtensionConfig(id="remote", label="Remote", description="desc", transport="http", url="http://x/mcp"),
    )

    data = settings_store.read_all(path, "extensions")
    assert data["remote"] == {"label": "Remote", "description": "desc", "url": "http://x/mcp"}


def test_save_extension_config_adds_a_new_stdio_entry(tmp_path: Path):
    path = _store(tmp_path, {})

    save_extension_config(
        path,
        ExtensionConfig(
            id="local", label="Local", description="desc", transport="stdio", command="python", args=["-m", "x"]
        ),
    )

    data = settings_store.read_all(path, "extensions")
    assert data["local"] == {"label": "Local", "description": "desc", "command": "python", "args": ["-m", "x"]}


def test_save_extension_config_overwrites_an_existing_entry_by_id(tmp_path: Path):
    path = _store(tmp_path, {"remote": {"label": "Old", "description": "", "url": "http://old/mcp"}})

    save_extension_config(
        path,
        ExtensionConfig(id="remote", label="New", description="", transport="http", url="http://new/mcp"),
    )

    assert settings_store.read_all(path, "extensions")["remote"]["url"] == "http://new/mcp"
    assert settings_store.read_all(path, "extensions")["remote"]["label"] == "New"


def test_save_extension_config_preserves_other_extension_entries(tmp_path: Path):
    path = _store(tmp_path, {"other": VALID_EXTENSIONS["other"]})

    save_extension_config(
        path, ExtensionConfig(id="remote", label="Remote", description="", transport="http", url="http://x/mcp")
    )

    data = settings_store.read_all(path, "extensions")
    assert data["other"] == VALID_EXTENSIONS["other"]
    assert "remote" in data


def test_delete_extension_config_removes_the_entry(tmp_path: Path):
    path = _store(tmp_path, {"remote": {"label": "Remote", "description": "", "url": "http://x/mcp"}})

    delete_extension_config(path, "remote")

    assert "remote" not in settings_store.read_all(path, "extensions")


def test_delete_extension_config_preserves_other_extension_entries(tmp_path: Path):
    path = _store(
        tmp_path,
        {
            "remote": {"label": "Remote", "description": "", "url": "http://x/mcp"},
            "other": VALID_EXTENSIONS["other"],
        },
    )

    delete_extension_config(path, "remote")

    data = settings_store.read_all(path, "extensions")
    assert "remote" not in data
    assert data["other"] == VALID_EXTENSIONS["other"]


def test_delete_extension_config_is_idempotent_for_an_unknown_id(tmp_path: Path):
    path = _store(tmp_path, {"other": VALID_EXTENSIONS["other"]})

    delete_extension_config(path, "does-not-exist")  # must not raise

    assert set(settings_store.read_all(path, "extensions")) == {"other"}


# --- capabilities ---
# The capabilities table toggles capabilities; a missing store or entry must mean enabled.


def test_capability_enabled_defaults_to_true_when_file_is_missing(tmp_path: Path):
    missing = tmp_path / "settings.db"

    assert capability_enabled(load_capabilities_config(missing), "otp") is True


def test_capability_enabled_defaults_to_true_when_entry_is_absent(tmp_path: Path):
    path = _caps(tmp_path, {"otp": {"enabled": True}})

    assert capability_enabled(load_capabilities_config(path), "host_health") is True


def test_capability_can_be_explicitly_disabled(tmp_path: Path):
    path = _caps(tmp_path, {"otp": {"enabled": False}})

    assert capability_enabled(load_capabilities_config(path), "otp") is False


def test_capability_explicitly_enabled_is_true(tmp_path: Path):
    path = _caps(tmp_path, {"otp": {"enabled": True}})

    assert capability_enabled(load_capabilities_config(path), "otp") is True


def test_save_capabilities_config_creates_a_missing_file(tmp_path: Path):
    """Must not require the file to exist: a fresh deployment's first toggle goes through this write path."""
    path = tmp_path / "settings.db"

    save_capabilities_config(path, "otp", False)

    assert load_capabilities_config(path) == {"otp": {"enabled": False}}


def test_save_capabilities_config_overwrites_an_existing_entry(tmp_path: Path):
    path = _caps(tmp_path, {"otp": {"enabled": True}})

    save_capabilities_config(path, "otp", False)

    assert load_capabilities_config(path) == {"otp": {"enabled": False}}


def test_save_capabilities_config_preserves_other_capabilities(tmp_path: Path):
    path = _caps(tmp_path, {"host_health": {"enabled": True}})

    save_capabilities_config(path, "otp", False)

    data = load_capabilities_config(path)
    assert data["host_health"] == {"enabled": True}
    assert data["otp"] == {"enabled": False}


def test_save_extension_config_keeps_the_token_and_repr_hides_it(tmp_path: Path):
    path = _store(tmp_path, {})
    config = ExtensionConfig(
        id="remote",
        label="Remote",
        description="desc",
        transport="http",
        url="http://x/mcp",
        headers={"X-Internal-Token": "s3$cret"},
    )

    save_extension_config(path, config)

    assert load_extensions_config(path)["remote"].headers == {"X-Internal-Token": "s3$cret"}
    assert "s3$cret" not in repr(config)


def test_forward_requester_defaults_false_and_parses_true(tmp_path: Path):
    path = _store(
        tmp_path,
        {
            "plain": {"label": "P", "url": "http://127.0.0.1:9000/mcp"},
            "http": {"label": "H", "url": "http://127.0.0.1:9001/mcp", "forward_requester": True},
            "local": {"label": "L", "command": "python", "forward_requester": True},
        },
    )

    loaded = load_extensions_config(path)

    assert loaded["plain"].forward_requester is False
    assert loaded["http"].forward_requester is True
    assert loaded["local"].forward_requester is True


def test_forward_requester_must_be_a_bool(tmp_path: Path):
    path = _store(tmp_path, {"remote": {"label": "R", "url": "http://x/mcp", "forward_requester": "yes"}})

    with pytest.raises(ValueError, match=r"'remote\.forward_requester' must be true or false"):
        load_extensions_config(path)


def test_web_url_defaults_to_none_and_parses_for_both_transports(tmp_path: Path):
    path = _store(
        tmp_path,
        {
            "plain": {"label": "P", "url": "http://127.0.0.1:9000/mcp"},
            "http": {"label": "H", "url": "http://127.0.0.1:9001/mcp", "web_url": " http://127.0.0.1:5174 "},
            "local": {"label": "L", "command": "python", "web_url": "https://tools.example/app"},
        },
    )

    loaded = load_extensions_config(path)

    assert loaded["plain"].web_url is None
    assert loaded["http"].web_url == "http://127.0.0.1:5174"
    assert loaded["local"].web_url == "https://tools.example/app"


@pytest.mark.parametrize(
    "bad",
    ["javascript:alert(1)", "ftp://host/app", "//host/app", "http://", "not a url", "", 5, ["http://x"]],
)
def test_web_url_must_be_an_http_or_https_url(tmp_path: Path, bad):
    path = _store(tmp_path, {"remote": {"label": "R", "url": "http://x/mcp", "web_url": bad}})

    with pytest.raises(ValueError, match=r"'remote\.web_url'"):
        load_extensions_config(path)


def test_web_url_survives_a_save(tmp_path: Path):
    path = _store(tmp_path, {})
    config = ExtensionConfig(
        id="remote", label="R", description="", transport="http", url="http://x/mcp", web_url="http://x:5174"
    )

    save_extension_config(path, config)

    assert load_extensions_config(path)["remote"].web_url == "http://x:5174"


def test_renamed_capability_keeps_its_state_under_the_new_id(tmp_path: Path):
    path = tmp_path / "settings.db"
    settings_store.put(path, "capabilities", "video", {"enabled": False})
    settings_store.put(path, "capabilities", "gen", {"enabled": True})
    migrate_renamed_capabilities(path)
    assert settings_store.read_all(path, "capabilities") == {"gen": {"enabled": True}, "media": {"enabled": False}}


def test_renamed_capability_does_not_override_a_new_entry_or_a_missing_file(tmp_path: Path):
    path = tmp_path / "settings.db"
    migrate_renamed_capabilities(path)
    assert not path.exists()
    settings_store.put(path, "capabilities", "video", {"enabled": False})
    settings_store.put(path, "capabilities", "media", {"enabled": True})
    migrate_renamed_capabilities(path)
    assert settings_store.read_all(path, "capabilities") == {"media": {"enabled": True}}


def test_save_email_settings_merges_checks_and_keeps_the_rest(tmp_path: Path):
    path = tmp_path / "settings.db"
    from src.services.app_config import save_email_settings
    save_email_settings(path, {"smtp_server": "smtp.example.com", "smtp_port": 587, "from": "a@example.com", "password": "pw"})

    saved = save_email_settings(path, {"smtp_port": 465, "password": None})

    assert saved == {"smtp_server": "smtp.example.com", "smtp_port": 465, "from": "a@example.com"}
    assert load_email_config(path).security == "ssl" and load_email_config(path).password == ""


def test_save_email_settings_refuses_a_bad_result_and_saves_nothing(tmp_path: Path):
    path = tmp_path / "settings.db"
    from src.services.app_config import email_document, save_email_settings
    save_email_settings(path, {"smtp_server": "smtp.example.com", "smtp_port": 587, "from": "a@example.com"})

    for bad in ({"smtp_port": "abc"}, {"security": "tls"}, {"from": None}, {"made_up": 1}):
        with pytest.raises((KeyError, ValueError)):
            save_email_settings(path, bad)

    assert email_document(path) == {"smtp_server": "smtp.example.com", "smtp_port": 587, "from": "a@example.com"}
