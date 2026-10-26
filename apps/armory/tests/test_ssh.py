"""Tests for services/ssh.py's security-relevant behavior; no network or SSH server.
They cover pure logic: how a command is quoted for a remote shell, and how the paramiko client is configured before connecting."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import paramiko
import pytest

from src.services.ssh import SSHClient, _new_client


# --- shell quoting ---
# run_login_shell() embeds a command in `/bin/bash -lc ...`; arguments come from an LLM that may read attacker-controlled text.


def _wrapped(command: str, shell: str = "bash") -> str:
    """Capture what run_login_shell() would actually execute."""
    client = SSHClient("host", "user", password="pw")
    client._client = MagicMock()
    captured: dict[str, str] = {}

    def fake_run(cmd: str):
        captured["cmd"] = cmd
        return MagicMock()

    client.run = fake_run  # type: ignore[method-assign]
    client.run_login_shell(command, shell=shell)
    return captured["cmd"]


def test_plain_command_is_wrapped_in_a_login_shell():
    assert _wrapped("uptime") == "/bin/bash -lc uptime"


def test_csh_variant_uses_csh():
    assert _wrapped("uptime", shell="csh") == "/bin/csh -c uptime"


@pytest.mark.parametrize(
    "payload",
    [
        'uptime"; rm -rf /tmp/x; echo "',   # closes the old double quote
        "uptime $(rm -rf /tmp/x)",           # command substitution
        "uptime `rm -rf /tmp/x`",            # backtick substitution
        "uptime && rm -rf /tmp/x",           # operator chaining
        "uptime; rm -rf /tmp/x",             # statement separator
        "uptime\nrm -rf /tmp/x",             # newline as separator
    ],
)
def test_injection_payloads_stay_a_single_argument(payload):
    """Each of these broke out of the old f'..."{command}"' wrapper; quoted, the payload is one argument to -c,
    so the remote shell runs it as a (failing) command name."""
    wrapped = _wrapped(payload)

    assert wrapped.startswith("/bin/bash -lc '")
    assert wrapped.endswith("'")
    # The dangerous text survives verbatim inside the quotes - it just
    # isn't shell syntax any more.
    inner = wrapped[len("/bin/bash -lc ") :]
    assert "rm -rf /tmp/x" in inner


def test_embedded_single_quote_is_escaped_not_dropped():
    wrapped = _wrapped("echo 'hi'")

    assert "'\"'\"'" in wrapped  # shlex's standard escape for a quote


# --- host key policy ---------------------------------------------------


def test_unknown_host_keys_are_rejected_by_default(tmp_path: Path):
    known = tmp_path / "known_hosts"
    known.touch()

    client = _new_client(known_hosts=known)

    assert isinstance(client._policy, paramiko.RejectPolicy)


def test_auto_policy_is_opt_in(tmp_path: Path):
    client = _new_client(known_hosts=tmp_path / "known_hosts", host_key_policy="auto")

    assert isinstance(client._policy, paramiko.AutoAddPolicy)


def test_auto_policy_creates_the_file_so_accepted_keys_persist(tmp_path: Path):
    """AutoAdd writes keys back only if the client knows the file, which paramiko learns from load_host_keys() (raises if missing).
    Otherwise trust-on-first-use would re-trust every connection and record nothing."""
    known = tmp_path / "nested" / "known_hosts"

    client = _new_client(known_hosts=known, host_key_policy="auto")

    assert known.exists()
    assert client._host_keys_filename == str(known)


def test_existing_known_hosts_entries_are_loaded(tmp_path: Path):
    known = tmp_path / "known_hosts"
    key = paramiko.RSAKey.generate(2048)
    known.write_text(f"example.com {key.get_name()} {key.get_base64()}\n", encoding="utf-8")

    client = _new_client(known_hosts=known)

    assert "example.com" in client.get_host_keys()


def test_missing_known_hosts_under_reject_policy_is_not_an_error(tmp_path: Path):
    """A missing file means "nothing trusted yet", which the reject policy handles; creating it is pointless since reject never writes."""
    known = tmp_path / "does-not-exist"

    client = _new_client(known_hosts=known)

    assert not known.exists()
    assert isinstance(client._policy, paramiko.RejectPolicy)


def test_unknown_policy_name_fails_loudly(tmp_path: Path):
    """A typo in SSH_HOST_KEY_POLICY must not quietly fall back to
    something permissive."""
    with pytest.raises(ValueError, match="expected 'reject' or 'auto'"):
        _new_client(known_hosts=tmp_path / "known_hosts", host_key_policy="ignore")


# --- port ---------------------------------------------------------------


def test_configured_port_reaches_paramiko(tmp_path: Path):
    """Regression: `port` was accepted in config.json then dropped (SSHClient had no port parameter), so hosts on non-standard ports connected to 22.
    Accepted-and-ignored config is worse than rejected."""
    known = tmp_path / "known_hosts"
    known.touch()
    client = SSHClient("h", "u", password="pw", port=2222, known_hosts=known)
    client._client = MagicMock()

    client._connect()

    assert client._client.connect.call_args.kwargs["port"] == 2222


def test_port_defaults_to_22(tmp_path: Path):
    known = tmp_path / "known_hosts"
    known.touch()
    client = SSHClient("h", "u", password="pw", known_hosts=known)
    client._client = MagicMock()

    client._connect()

    assert client._client.connect.call_args.kwargs["port"] == 22
